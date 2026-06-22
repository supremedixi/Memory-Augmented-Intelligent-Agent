# Memory-Augmented-Intelligent-Agent
A memory-augmented AI email agent.
# MailGraph: Memory-Augmented AI Email Agent

MailGraph is a 24/7 automated digital email twin driven by a LangGraph state machine. It not only performs millisecond-level email monitoring but also accurately understands context using short and long-term memory. It automatically filters noise, highlights key notifications and pushes them to WeChat, and can even draft professional replies mimicking your tone.

> **Say goodbye to polling delays and information anxiety. Hand over your inbox management entirely to deterministic workflows.**

---

## 🌟 Key Features

* ⚡️ **Zero-Latency Listening (Hybrid IDLE Polling):** Abandons inefficient scheduled polling. Utilizes the underlying `IMAP IDLE` protocol combined with a custom `NOOP` heartbeat mechanism to bypass NAT limits, achieving sub-second new email perception.
* 🧠 **State Machine Driven (DAG Workflow):** Rejects LLM "black-box" execution. Built on a rigorous directed acyclic graph (DAG) using LangGraph, breaking down "perception-decision-action" into deterministic nodes to eliminate infinite loops and hallucinated overreach.
* 🛡️ **Safety Guardrails (Sandboxed Execution):** The agent only possesses permission to operate within the "Drafts" folder (`draft_only=True`). Drafts are silently uploaded to the cloud drafts box awaiting final human confirmation (Human-in-the-Loop), strictly preventing unauthorized email dispatch.
* 🔔 **Noise Reduction & WeChat Push:** Dehydrates and compresses lengthy verification codes, system alerts, and meeting notifications, pushing them to WeChat with millisecond latency via the PushPlus API to protect your attention.
* 🗄️ **Persistent Memory:** Integrates with PostgreSQL / pgvector to automatically accumulate and retrieve historical conversations and prompt optimizations, understanding your writing style better over time.

---

## 🛠️ Quick Start

### 1. Environment Setup

Ensure your system has Python 3.10 or higher installed (using Anaconda or a virtual environment is highly recommended). You will also need access to a PostgreSQL database for memory persistence.

Clone the repository and install the required dependencies:

```bash
git clone https://github.com/yourusername/MailGraph.git
cd MailGraph
python -m pip install -r requirements.txt

```

### 2. Environment Variables Configuration

Copy the example environment file to create your own configuration:

```bash
cp .env.example .env

```

Open the `.env` file with your preferred text editor and configure your specific credentials:

```env
# --- Email Configuration (e.g., QQ Mail / Gmail) ---
IMAP_SERVER="imap.qq.com"
EMAIL_ACCOUNT="your_email@qq.com"
EMAIL_PASSWORD="your_app_password"
SMTP_HOST="smtp.qq.com"
SMTP_PORT=465
SMTP_USER="your_email@qq.com"
SMTP_PASSWORD="your_app_password"

# --- LLM Configuration (DeepSeek) ---
LLM_MODEL="deepseek-chat"
DEEPSEEK_API_KEY="sk-xxxxxx"
LLM_BASE_URL="https://api.deepseek.com/v1"

# --- Notification Configuration ---
PUSHPLUS_TOKEN="your_pushplus_token"

# --- Database Configuration (Supabase / PostgreSQL) ---
POSTGRES_DB_URI="postgresql://user:password@host:port/dbname"

```

### 3. Run the Agent

Once the setup is complete, start your digital assistant:

```bash
python main.py

```

When the console prints `⏳ Entering IDLE long-connection mode, listening for new emails...`, your agent has successfully entered its stealth monitoring state.
