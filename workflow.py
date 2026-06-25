import os
import time
from typing import Literal, Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langchain.agents import create_agent
from langmem import create_manage_memory_tool, create_search_memory_tool
from config import llm, store, logger, agent_config, shared_state
from state import State, ActionHistory
from skills.scheduler_tools import schedule_event_reminder
from skills.email_tools import write_email

from utils.feishu_api import send_feishu_message

def load_skill_md(filename: str) -> str:
    filepath = os.path.join(os.path.dirname(__file__), "skills", filename)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"严重错误：找不到技能文件 {filename}: {e}")
        return ""

manage_memory = create_manage_memory_tool(namespace=("email_assistant", "{langgraph_user_id}", "collection"))
search_memory = create_search_memory_tool(namespace=("email_assistant", "{langgraph_user_id}", "collection"))
local_tools = [write_email, manage_memory, search_memory]

response_agent = None 

class Router(BaseModel):
    reasoning: str = Field(description="逐步推理过程")
    classification: Literal["ignore", "respond", "notify"] = Field(description="分类结果")
    notification_summary: str = Field(default="", description="简述要通知的核心内容")

    event_time: Optional[str] = Field(
        default=None, 
        description="如果是日程或会议，必须提取精确时间，格式为 'YYYY-MM-DD HH:MM:SS'。如无法确定则为 null。"
    )
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    priority: int = Field(default=3, ge=1, le=5)

    @field_validator("classification", mode="before")
    @classmethod
    def normalize_classification(cls, v: str) -> str:
        v = v.strip().lower()
        return v if v in ("ignore", "respond", "notify") else "respond"

llm_router = llm.with_structured_output(Router, method="function_calling")

async def triage_node(state: State, config: RunnableConfig) -> dict:
    email = state["email_input"]
    user_id = config["configurable"]["langgraph_user_id"]
    
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

    raw_prompt = load_skill_md("email_triage.md")
    if not raw_prompt:
        raw_prompt = "请分类以下邮件：发件人:{author}, 主题:{subject}, 正文:{email_thread}"

    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prompt = raw_prompt.format(
        author=email.get('author', ''),
        subject=email.get('subject', ''),
        email_thread=email.get('email_thread', ''),
        attachments=", ".join(email.get('attachments', [])) or "无附件",
        examples=formatted_examples or "无",
        current_time=current_time_str
    )

    for attempt in range(agent_config.llm_max_retries):
        try:
            result = await llm_router.ainvoke([HumanMessage(content=prompt)])
            return {
                "triage_result": result.classification,
                "triage_confidence": result.confidence,
                "notification_summary": getattr(result, "notification_summary", ""),
                "event_time": getattr(result, "event_time", None), 
                "action_history": [ActionHistory(node="triage", action=result.classification)]
            }
        except Exception as e:
            logger.warning(f"分类失败重试 ({attempt}): {e}")
            time.sleep(1)
            
    return {"triage_result": "respond", "triage_confidence": 0.0}

def notify_node(state: State, config: RunnableConfig) -> dict:
    email = state.get("email_input", {})
    summary = state.get("notification_summary", "收到一条重要通知，请检查邮箱。")
    event_time_str = state.get("event_time")
    
    author = email.get('author', '未知发件人')
    subject = email.get('subject', '无主题')

    if event_time_str:
        logger.info(f"检测到未来日程，写入时间日程: {event_time_str}")
        immediate_msg = f"**发件人**: {author}\n**内容**: \n> {summary}\n\n*已写入本地数据库，将在 {event_time_str} 及提前一天发送强提醒。*"
        send_feishu_message(f"日程已收录: {subject[:15]}...", immediate_msg)
        schedule_event_reminder(subject, event_time_str, author)
    else:
        logger.info(f"[即时通知] 主题: {subject}")
        immediate_msg = f"**发件人**: {author}\n**内容**: \n> {summary}"
        send_feishu_message(f" 邮件提醒: {subject[:15]}...", immediate_msg)
    
    return {"action_history": [ActionHistory(node="notify", action="pushed_notification")]}

async def response_node(state: State, config: RunnableConfig) -> dict:
    user_id = config["configurable"]["langgraph_user_id"]
    email = state.get("email_input", {})
    
    stored = store.get(("email_assistant", user_id, "prompts"), "response_prompt")
    procedural_instructions = stored.value if stored else "请根据上下文专业回复。"

    raw_prompt = load_skill_md("email_reply.md")
    if not raw_prompt:
        raw_prompt = "指令: {procedural_instructions}\n主题: {subject}"

    dynamic_prompt = raw_prompt.format(
        procedural_instructions=procedural_instructions,
        subject=email.get('subject', '无主题'),
        author=email.get('author', '未知'),
        email_thread=email.get('email_thread', ''),
        attachments=", ".join(email.get('attachments', [])) or "无附件"
    )
    
    enriched_state = {
        **state, 
        "messages": [SystemMessage(content=dynamic_prompt)] + state.get("messages", [])
    }

    global response_agent

    agent_result = await response_agent.ainvoke(enriched_state) 
    ai_reply_text = agent_result["messages"][-1].content
    
    draft_info = shared_state.get("last_email", {})
    real_draft_content = draft_info.get("content", "大模型未调用邮件工具，未能截获草稿。")
    feishu_msg = (
        f"**发件人**: {email.get('author')}\n"
        f"**主题**: {email.get('subject')}\n\n"
        f"**真实回复草稿（点击发送将发出此内容）：**\n---\n{real_draft_content}\n---\n\n"
        f"**智能体审稿/执行留言：**\n{ai_reply_text}"
    )
    send_feishu_message("草稿已生成等待审核", feishu_msg)
    
    agent_result["notification_summary"] = "草稿已生成。"
    return agent_result

def route_based_on_triage(state: State) -> str:
    res = state.get("triage_result", "respond")
    if res == "respond":
        return "response_node"
    elif res == "notify":
        return "notify_node"
    else:
        return END

def create_email_workflow(mcp_tools=None):
    if mcp_tools is None:
        mcp_tools = []
        
    all_tools = local_tools + mcp_tools
    
    global response_agent
    response_agent = create_agent(model=llm, tools=all_tools, store=store)
    
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

from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage
from config import llm, store, logger

# 定义大模型提取规则的数据结构
class RuleExtraction(BaseModel):
    new_rule: str = Field(description="根据用户的批评/建议，提炼出的核心行为规范。必须简明扼要，例如'回复语气必须委婉客气'或'拒绝邀请时必须附带抱歉的理由'。如无实质规则可提取则返回空。")

def optimize_prompts(feedback: str, user_id: str):
    logger.info(f"收到飞书反馈: 「{feedback}」，准备提炼并追加新规则...")

    response_entry = store.get(("email_assistant", user_id, "prompts"), "response_prompt")
    current_prompt = response_entry.value if response_entry else "请根据上下文专业回复。\n\n【专属行为规范】"

    extractor = llm.with_structured_output(RuleExtraction, method="function_calling")
    extraction_prompt = (
        f"用户对你刚才写的邮件草稿提出了批评或修改建议：\n「{feedback}」\n\n"
        "请将这个具体的建议，提炼成一条通用的【行为规范/规则】，以便未来写邮件时永远遵守此规则。"
    )
    
    try:
        result = extractor.invoke([HumanMessage(content=extraction_prompt)])
        new_rule = result.new_rule
        
        if new_rule:
            # 3. 核心机制：在旧规则的基础上，安全追加新规则！绝对不修改、不删减旧内容。
            improved_response = f"{current_prompt}\n- {new_rule}"
            
            # 存入记忆数据库
            store.put(("email_assistant", user_id, "prompts"), "response_prompt", improved_response)
            logger.info(f"成功在原有基础上追加新规则: {new_rule}")
        else:
            logger.info(" 反馈中未提取到通用规则，指令保持不变。")
            
    except Exception as e:
        logger.error(f"规则提取与追加失败: {e}")

def initialize_prompts(user_id: str):
    if not store.get(("email_assistant", user_id, "prompts"), "response_prompt"):
        store.put(("email_assistant", user_id, "prompts"), "response_prompt", "根据发件人语气灵活调整，优先简明扼要。")
