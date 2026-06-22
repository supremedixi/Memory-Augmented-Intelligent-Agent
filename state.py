import operator
from datetime import datetime
from typing import TypedDict, Annotated
from pydantic import BaseModel, Field
from langgraph.graph import add_messages

class EmailMetadata(BaseModel):
    email_id: str = ""
    received_at: str = ""
    priority_score: float = 0.0
    sentiment: str = "neutral"
    sender_domain: str = ""

class ActionHistory(BaseModel):
    node: str
    action: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    detail: str = ""
    success: bool = True

class State(TypedDict):
    email_input: dict
    messages: Annotated[list, add_messages] # 用于合并对话消息
    
    triage_result: str 
    triage_confidence: float
    triage_reasoning: str
    notification_summary: str
    
    email_metadata: EmailMetadata
    action_history: Annotated[list, operator.add] # 必须用 operator.add 合并普通列表
    
    error_count: int
    max_retries: int