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
    messages: Annotated[list, add_messages]
    
    triage_result: str 
    triage_confidence: float
    triage_reasoning: str
    notification_summary: str
    
    email_metadata: EmailMetadata
    action_history: Annotated[list, operator.add]
    
    error_count: int
    max_retries: int
