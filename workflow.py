import time
from typing import Literal, List
import requests
import os
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langchain.agents import create_agent
from langmem import create_multi_prompt_optimizer

from config import llm, store, logger, agent_config
from state import State, EmailMetadata, ActionHistory
from tools import tools_list

# ================= Triage 分拣节点定义 =================
class Router(BaseModel):
    reasoning: str = Field(description="逐步推理过程")
    classification: Literal["ignore", "respond", "notify"] = Field(description="分类结果")
    notification_summary: str = Field(default="", description="如果是notify，简述要通知的核心内容（如：XX网站的验证码是123456）")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    priority: int = Field(default=3, ge=1, le=5)

    @field_validator("classification", mode="before")
    @classmethod
    def normalize_classification(cls, v: str) -> str:
        v = v.strip().lower()
        return v if v in ("ignore", "respond", "notify") else "respond"

llm_router = llm.with_structured_output(Router, method="function_calling")

TRIAGE_PROMPT = PromptTemplate.from_template("""你是一个极其严谨的首席邮件分拣秘书。你的首要任务是保护用户的注意力，同时【绝对不能漏掉任何一封潜在的重要邮件】。

请先仔细阅读待分类邮件，进行逐步推理（reasoning），然后按以下核心规则进行分类提取：

【核心分类规则】
1. 类别：'respond' (需要回复)
   - 适用场景：真人发来的提问、工作指派、商务沟通、需要确认 RSVP 的邀请等。
   - 动作：只要邮件暗示或明确需要用户采取行动、做出决定或写信回复，立刻归入此条。

2. 类别：'notify' (需强提醒 / 重要查阅)
   - 适用场景：验证码、系统告警、会议/日程通知、财务账单/发票、行程单、审核通过/拒绝通知、账号安全提示等。
   - 动作：不需要用户回信，但【用户必须知晓】。
   - 强制提取：必须在 notification_summary 字段中输出极致精简的摘要，格式为：“[发件平台/人物]：核心事件内容/数据”。

3. 类别：'ignore' (直接忽略)
   - 适用场景：纯粹的推销广告、恶意钓鱼邮件、毫无营养的系统凑数邮件（如“您有一条未读系统消息”且无上下文）。
   - ⚠️ 绝对兜底原则：如果你只有 80% 的把握它是垃圾邮件，剩下 20% 觉得可能对用户有用，【请绝对不要归为 ignore，宁可错杀归为 notify】！

【历史参考示例】
{examples}

【待分类邮件】
发件人: {author}
主题: {subject}
正文: {email_thread}
""")

def triage_node(state: State, config: RunnableConfig) -> dict:
    email = state["email_input"]
    user_id = config["configurable"]["langgraph_user_id"]
    
    # 检索情景记忆
    examples = store.search(
        ("email_assistant", user_id, "examples"),
        query=f"{email.get('subject', '')}",
        limit=agent_config.memory_max_examples,
    )
    
    formatted_examples = ""
    for eg in examples:
        if getattr(eg, "score", 1.0) >= agent_config.memory_similarity_threshold:
            em = eg.value.get("email", {})
            label = eg.value.get("label", "unknown")
            formatted_examples += f"内容: {em.get('email_thread', '')[:300]} -> 分类: {label}\n"

    prompt = TRIAGE_PROMPT.format(examples=formatted_examples or "无", **email)
    
    # 带重试的调用
    for attempt in range(agent_config.llm_max_retries):
        try:
            result = llm_router.invoke([HumanMessage(content=prompt)])
            return {
                "triage_result": result.classification,
                "triage_confidence": result.confidence,
                "notification_summary": result.notification_summary if hasattr(result, "notification_summary") else "",
                "action_history": [ActionHistory(node="triage", action=result.classification)]
            }
        except Exception as e:
            logger.warning(f"分类失败重试 ({attempt}): {e}")
            time.sleep(1)
            
    return {"triage_result": "respond", "triage_confidence": 0.0}

def notify_node(state: State, config: RunnableConfig) -> dict:
    email = state.get("email_input", {})
    summary = state.get("notification_summary", "收到一条重要通知，请检查邮箱。")

    author = email.get('author', '未知发件人')
    subject = email.get('subject', '无主题')

    logger.info(f"🔔 [通知归档] 主题: {subject} | 提取内容: {summary}")

    pushplus_token = os.getenv("PUSHPLUS_TOKEN")
    if pushplus_token:
        # 构建推送标题和正文
        title = f"🔔 邮件提醒: {subject[:20]}..."
        content = f"**发件人**: {author}\n\n**核心提取**: \n> {summary}\n\n---\n*由你的专属邮件智能体推送*"
        
        url = "http://www.pushplus.plus/send"
        payload = {
            "token": pushplus_token,
            "title": title,
            "content": content,
            "template": "markdown" # 使用 markdown 渲染更美观
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info("✅ 验证码/通知已成功推送到微信！")
            else:
                logger.warning(f"⚠️ 微信推送返回异常: {response.text}")
        except Exception as e:
            logger.error(f"❌ 微信通知发送失败: {e}")
    else:
        logger.warning("⚠️ PUSHPLUS_TOKEN 未配置，无法发送微信通知。")
    
    return {"action_history": [ActionHistory(node="notify", action="pushed_notification")]}

# ================= Response 回复节点定义 =================
DEFAULT_RESPONSE_PROMPT = "你是一个专业的邮件助手。请根据邮件内容帮助用户撰写回复或安排日程。"
response_agent = create_agent(model=llm, tools=tools_list, system_prompt=DEFAULT_RESPONSE_PROMPT, store=store)

def response_node(state: State, config: RunnableConfig) -> dict:
    user_id = config["configurable"]["langgraph_user_id"]
    email = state.get("email_input", {})
    
    # 提取程序性记忆
    stored = store.get(("email_assistant", user_id, "prompts"), "response_prompt")
    procedural_instructions = stored.value if stored else DEFAULT_RESPONSE_PROMPT
    
    # 强制拼接在最后，确保无论智能体怎么自我进化，这条安全规则绝对不会被遗忘或覆盖
    # 完全信任智能体之后，只需要把 SAFETY_GUARDRAIL 里的这段字符串删掉或注释掉，就变成可以全自动秒发邮件
    SAFETY_GUARDRAIL = (
        "\n\n【⚠️ 绝对安全护栏】\n"
        "1. 调用 write_email 工具时，必须严格将 `draft_only` 参数设置为 True。\n"
        "2. 绝对不允许直接发送真实的邮件！你只负责生成回复草稿供我稍后审核。"
    )
    
    dynamic_prompt = (
        f"当前处理邮件主题: {email.get('subject')}\n\n"
        f"【工作指令】\n{procedural_instructions}"
        f"{SAFETY_GUARDRAIL}"
    )
    
    enriched_state = {
        **state, 
        "messages": [SystemMessage(content=dynamic_prompt)] + state.get("messages", [])
    }
    
    # 1. 让智能体执行写草稿任务
    agent_result = response_agent.invoke(enriched_state)
    agent_result["notification_summary"] = "✅ 智能体已为您自动起草了回复，请在闲暇时前往邮箱草稿箱查看并发送。"
    
    return agent_result

# ================= 构建 LangGraph =================
def route_based_on_triage(state: State) -> str:
    res = state.get("triage_result", "respond")
    if res == "respond":
        return "response_node"
    elif res == "notify":
        return "notify_node"
    else:
        return END

def create_email_workflow():
    workflow = StateGraph(State)
    workflow.add_node("triage", triage_node)
    workflow.add_node("response_node", response_node)
    workflow.add_node("notify_node", notify_node)
    
    workflow.add_edge(START, "triage")
    workflow.add_conditional_edges("triage", route_based_on_triage, {
        "response_node": "response_node", 
        "notify_node": "notify_node", 
        END: END
    })
    workflow.add_edge("response_node", "notify_node")
    workflow.add_edge("notify_node", END)
    
    return workflow.compile(store=store)

# ================= 提示词优化 (程序性记忆) =================
def optimize_prompts(feedback: str, user_id: str):
    logger.info("开始基于反馈重写系统指令...")
    triage_entry = store.get(("email_assistant", user_id, "prompts"), "triage_prompt")
    response_entry = store.get(("email_assistant", user_id, "prompts"), "response_prompt")
    
    t_prompt = triage_entry.value if triage_entry else TRIAGE_PROMPT.template
    r_prompt = response_entry.value if response_entry else DEFAULT_RESPONSE_PROMPT
    
    optimizer = create_multi_prompt_optimizer(llm)
    trajectories = [([{"role": "system", "content": r_prompt}], {"feedback": feedback})]
    prompts = [{"name": "response", "prompt": r_prompt}]
    
    try:
        result = optimizer.invoke({"trajectories": trajectories, "prompts": prompts})
        improved_response = next((p["prompt"] for p in result if p["name"] == "response"), r_prompt)
        store.put(("email_assistant", user_id, "prompts"), "response_prompt", improved_response)
        logger.info("✅ 程序性记忆（指令）已成功进化！")
    except Exception as e:
        logger.error(f"优化失败: {e}")

def initialize_prompts(user_id: str):
    if not store.get(("email_assistant", user_id, "prompts"), "triage_prompt"):
        store.put(("email_assistant", user_id, "prompts"), "triage_prompt", TRIAGE_PROMPT.template)
        store.put(("email_assistant", user_id, "prompts"), "response_prompt", DEFAULT_RESPONSE_PROMPT)