import os
import sys
import logging
from dataclasses import dataclass
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langgraph.store.postgres import PostgresStore
from psycopg_pool import ConnectionPool

logging.getLogger("langchain_openai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com") 

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("email_agent.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("EmailAgent")

load_dotenv()

@dataclass
class AgentConfig:
    llm_model: str = os.getenv("LLM_MODEL", "deepseek-chat")
    llm_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.3
    llm_timeout: int = 120
    llm_max_retries: int = 3

    embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
    hf_token: str = os.getenv("HF_TOKEN", "") 
    
    memory_max_examples: int = 5
    memory_similarity_threshold: float = 0.3
    memory_max_chars_per_example: int = 300

agent_config = AgentConfig()

if not agent_config.llm_api_key:
    raise ValueError(" LLM API Key 未设置！请在 .env 文件中配置 DEEPSEEK_API_KEY")

llm = ChatOpenAI(
    model=agent_config.llm_model,
    api_key=agent_config.llm_api_key,
    base_url=agent_config.llm_base_url,
    max_tokens=agent_config.llm_max_tokens,
    temperature=agent_config.llm_temperature,
    timeout=agent_config.llm_timeout,
    max_retries=agent_config.llm_max_retries,
)

if not agent_config.hf_token:
    logger.warning(" 未设置 HF_TOKEN。在线向量 API 可能会调用失败或受到严重的速率限制。")

embeddings = HuggingFaceEndpointEmbeddings(
    model=agent_config.embedding_model,
    task="feature-extraction",
    huggingfacehub_api_token=agent_config.hf_token
)

db_uri = os.getenv("POSTGRES_DB_URI", "")
if not db_uri:
    raise ValueError(" POSTGRES_DB_URI 未设置！请检查您的 .env 配置。")

# 建立到 Supabase 的长连接池 (注意：端口必须是 5432)
pool = ConnectionPool(conninfo=db_uri)

store = PostgresStore(
    conn=pool,
    index={
        "embed": embeddings,
        "dims": 512,
    }
)

store.setup()
shared_state = {"last_email": None}
logger.info(" 基础配置、大语言模型与在线向量存储初始化完成")
