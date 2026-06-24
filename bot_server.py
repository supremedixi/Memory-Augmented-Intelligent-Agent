# bot_server.py
import os
import json
import logging
import threading
from lark_oapi import ws
import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from pydantic import BaseModel, Field
from typing import Literal
from langchain_core.messages import HumanMessage, SystemMessage
from config import llm, shared_state, logger
from workflow import optimize_prompts, response_agent
from workflow import optimize_prompts
from utils.feishu_api import send_feishu_message
from config import shared_state
from skills.email_tools import write_email

LAST_EMAIL_STATE = {}

class IntentRouter(BaseModel):
    intent: Literal["send_email", "modify_draft", "chat"] = Field(
        description="""
        精准判断用户的意图：
        - send_email: 用户明确同意、批准发送当前的邮件草稿（如：“发吧”、“没问题，发送”、“OK”）。注意：如果是“把草稿发给我看”，这是chat，不是send_email！
        - modify_draft: 用户对当前的草稿提出了具体的修改意见、语气要求、或者补充信息（如：“语气客气点”、“末尾加上祝周末愉快”、“我不去开会了，帮我拒绝”）。
        - chat: 用户只是在闲聊、提问、或者要求查看草稿内容（如：“把草稿给我看看”、“你是谁”）。
        """
    )
    feedback: str = Field(
        default="", 
        description="如果 intent 是 modify_draft，请提取出用户具体的修改要求；否则留空。"
    )

def process_bot_command(user_text: str, open_id: str):
    """处理用户指令的核心业务逻辑（支持全自然语言）"""

    draft = shared_state.get("last_email")
    context_str = f"当前有一封写给 {draft['to']} 的邮件草稿待审核。" if draft else "当前没有任何草稿。"

    logger.info(f"正在分析用户意图: 「{user_text}」")
    router_llm = llm.with_structured_output(IntentRouter, method="function_calling")
    prompt = f"【系统上下文】\n{context_str}\n\n【用户在飞书发来的消息】\n「{user_text}」\n\n请判断用户的真实意图。"
    
    try:
        decision = router_llm.invoke([HumanMessage(content=prompt)])
        logger.info(f"意图识别结果: {decision.intent}")
    except Exception as e:
        logger.error(f"意图识别失败: {e}")
        send_feishu_message("系统异常", "意图识别失败，请稍后再试。", open_id)
        return

    # ================= 分支 A：确认发送 =================
    if decision.intent == "send_email":
        if not draft:
            send_feishu_message("发送失败", "内存中没有找到最近的草稿。", open_id)
            return
            
        send_feishu_message("⏳ 正在执行", "正在通过 SMTP 发送真实邮件，请稍候...", open_id)
        try:
            result_msg = write_email.invoke({
                "to": draft["to"],
                "subject": draft["subject"],
                "content": draft["content"],
                "draft_only": False # 触发真实发送
            })
            send_feishu_message("邮件发送成功", f"执行结果：\n{result_msg}", open_id)
            shared_state["last_email"] = None 
        except Exception as e:
            send_feishu_message("发送异常", f"底层发送失败：{e}", open_id)

    # ================= 分支 B：修改草稿并进化 =================
    elif decision.intent == "modify_draft":
        feedback = decision.feedback or user_text
        send_feishu_message("正在重写草稿", f"已收到修改建议:\n「{feedback}」\n正在为您重新拟定，请稍候...", open_id)
        
        # 1. 触发长效记忆更新
        optimize_prompts(feedback, "admin_user")
        
        # 2. 重新调用大模型重写草稿
        if draft:
            enriched_state = {
                "email_input": {"author": draft["to"], "subject": draft["subject"].replace("Re: ", "")},
                "messages": [SystemMessage(content=f"用户反馈修改意见：{feedback}。请严格结合此意见，重写邮件回复草稿。")]
            }
            try:生成
                agent_result = response_agent.invoke(enriched_state)
                new_reply = agent_result["messages"][-1].content
                shared_state["last_email"]["content"] = new_reply
                
                send_feishu_message(
                    "修改完成等待审核", 
                    f"**新草稿内容：**\n---\n{new_reply}\n---\n如果不满意可继续提出修改意见，满意请直接回复“发吧”", 
                    open_id
                )
            except Exception as e:
                send_feishu_message("重写失败", f"大模型调用异常: {str(e)}", open_id)
        else:
            send_feishu_message("记忆已更新", "您的偏好已记录，将在收到下一封邮件时生效。", open_id)

    # ================= 分支 C：普通对话聊天 =================
    else:
        system_prompt = SystemMessage(content=f"""
        你是一个专业、贴心的私人邮件助理。用户正在通过手机飞书和你聊天。
        请根据用户的提问直接做出回答。如果用户想看草稿，请直接把草稿内容完整地发给它。
        【当前草稿状态】
        {context_str}
        如果存在草稿，内容为：
        {draft['content'] if draft else '无'}
        """)
        try:
            response = llm.invoke([system_prompt, HumanMessage(content=user_text)])
            send_feishu_message("助理", response.content, open_id)
        except Exception as e:
            logger.error(f"对话异常: {e}")

def handle_message(data: P2ImMessageReceiveV1) -> None:
    """飞书长连接的回调函数：每当有人给机器人发消息，就会触发这里"""
    try:
        open_id = data.event.sender.sender_id.open_id
        content_str = data.event.message.content
        content_dict = json.loads(content_str)
        user_text = content_dict.get("text", "").strip()
        
        logger.info(f"收到飞书消息 [{open_id}]: {user_text}")

        threading.Thread(target=process_bot_command, args=(user_text, open_id), daemon=True).start()
        
    except Exception as e:
        logger.error(f"处理飞书消息异常: {e}")

def start_feishu_websocket():
    """启动飞书长连接客户端"""
    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")
    
    if not app_id or not app_secret:
        logger.error("缺少 FEISHU_APP_ID 或 FEISHU_APP_SECRET，无法启动机器人长连接。")
        return

    event_handler = lark.EventDispatcherHandler.builder("", "") \
        .register_p2_im_message_receive_v1(handle_message) \
        .build()

    logger.info("正在与飞书服务器建立 WebSocket 长连接...")
    cli = ws.Client(
        app_id, 
        app_secret, 
        event_handler=event_handler, 
        log_level=lark.LogLevel.WARNING # 屏蔽掉底层网络库的刷屏日志
    )
    cli.start() # 注意：这是一个阻塞方法，它会永远运行下去保持连接
