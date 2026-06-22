import os
import sys
import logging
from dataclasses import dataclass
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_huggingface import HuggingFaceEmbeddings
from langgraph.store.memory import InMemoryStore

# ----- 强制离线加载模型 -----
os.environ["HF_HUB_OFFLINE"] = "1"          # 禁止联网
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com") 

# ----- 日志设置 -----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("email_agent.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("EmailAgent")

# ----- 加载环境变量 -----
load_dotenv()

# ----- 配置类 -----
@dataclass
class AgentConfig:
    llm_model: str = os.getenv("LLM_MODEL", "deepseek-chat")
    llm_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.3
    llm_timeout: int = 60
    llm_max_retries: int = 3
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
    memory_max_examples: int = 5
    memory_similarity_threshold: float = 0.3
    memory_max_chars_per_example: int = 300

agent_config = AgentConfig()
if not agent_config.llm_api_key:
    raise ValueError("❌ LLM API Key 未设置！请在 .env 中设置 DEEPSEEK_API_KEY")

# ----- 实例化全局单例 -----
llm = ChatOpenAI(
    model=agent_config.llm_model,
    api_key=agent_config.llm_api_key,
    base_url=agent_config.llm_base_url,
    max_tokens=agent_config.llm_max_tokens,
    temperature=agent_config.llm_temperature,
    timeout=agent_config.llm_timeout,
    max_retries=agent_config.llm_max_retries,
)

# 使用本地缓存加载模型（强制离线）
embeddings = HuggingFaceEmbeddings(
    model_name=agent_config.embedding_model,
    model_kwargs={"local_files_only": True}
)

store = InMemoryStore(index={"embed": embeddings, "dims": 512})

logger.info("✅ 基础配置、LLM 与记忆存储初始化完成")