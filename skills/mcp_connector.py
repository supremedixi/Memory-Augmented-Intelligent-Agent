import logging
from typing import List
from contextlib import AsyncExitStack

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger("EmailAgent")

class MultiMCPManager:
    """
    多节点 MCP 服务器生命周期管理器
    负责统一启动、管理和释放多个 MCP Server 的长连接
    """
    def __init__(self):
        self.stack = AsyncExitStack()
        self.sessions: List[ClientSession] = []
        self.tools: List[BaseTool] = []
        
        # 定义需要挂载的 MCP 能力矩阵
        self.server_configs = [
            # 1. 深度文档解析能力 (纯本地，无需联网)
            # 通过 npx 调用官方文件系统 Server，并暴露当前目录下的 downloads 文件夹给大模型
            {
                "name": "Local_FileSystem",
                "command": "npx",
                "args": [
                    "-y", 
                    "@modelcontextprotocol/server-filesystem", 
                    "./downloads",   # 允许智能体读取邮件自动保存的附件
                    "./documents"    # 你可以手动建立此文件夹，放一些背景知识供其查阅
                ]
            }
        ]

    async def initialize(self) -> List[BaseTool]:
        """异步初始化所有配置好的 MCP 服务器"""
        logger.info("🔌 正在启动 MCP 扩展能力阵列...")
        
        for config in self.server_configs:
            server_name = config["name"]
            try:
                server_params = StdioServerParameters(
                    command=config["command"],
                    args=config["args"]
                )

                # 1. 创建 stdio 传输管道并推入栈 (保证最后能安全关闭)
                stdio_transport = await self.stack.enter_async_context(stdio_client(server_params))
                read, write = stdio_transport

                # 2. 创建 JSON-RPC 通信 Session 并推入栈
                session = await self.stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                self.sessions.append(session)

                # 3. 拉取该 MCP Server 暴露的所有工具并转换为 LangChain 工具
                mcp_tools = await load_mcp_tools(session)
                self.tools.extend(mcp_tools)
                
                logger.info(f"✅ 成功挂载 MCP 节点 [{server_name}] -> 已载入 {len(mcp_tools)} 个增强工具")
            
            except Exception as e:
                logger.error(f"❌ 挂载 MCP 节点 [{server_name}] 失败: {e}")
                logger.warning("提示: 确保你的电脑已安装 Node.js，因为运行 npx 需要 Node 环境。")

        logger.info(f"MCP 初始化完成，总计提供 {len(self.tools)} 个跨界调用能力。")
        return self.tools

    async def cleanup(self):
        """安全释放所有资源，防止僵尸进程驻留在后台"""
        if self.sessions:
            logger.info("正在安全切断所有 MCP 管道连接...")
            await self.stack.aclose()
            self.sessions.clear()
            self.tools.clear()
            logger.info("✅ MCP 资源已安全释放。")