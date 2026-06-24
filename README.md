This is a massive leap forward! Your current README reflects the *V1* of your project. Since we've completely upgraded the architecture to include **Feishu (Lark) WebSocket two-way communication**, **MCP (Model Context Protocol) tool integration**, **Smart APScheduler event reminders**, and **Rule-Append Evolutionary Memory**, the README needs a major rewrite to showcase these cutting-edge features.

Here is the fully optimized and updated `README.md` for your V2 architecture:

---

# MailGraph: Memory-Augmented AI Email Agent

MailGraph is a 24/7 automated digital email twin driven by a LangGraph state machine. It not only performs millisecond-level email monitoring but also accurately understands context using short and long-term memory. It automatically filters noise, schedules meeting reminders, reads local attachments via MCP, and pushes notifications directly to your Feishu (Lark) app.

> **Say goodbye to polling delays and information anxiety. Hand over your inbox management to a deterministic workflow with a perfect Two-Way Human-in-the-Loop experience.**

---

## 🌟 Key Features

* ⚡️ **Zero-Latency Listening (Hybrid IDLE Polling):** Abandons inefficient scheduled polling. Utilizes the underlying `IMAP IDLE` protocol combined with a custom `NOOP` heartbeat mechanism to bypass NAT limits, preventing silent connection drops and achieving sub-second new email perception.
* 📱 **Two-Way Human-in-the-Loop (Feishu Native):** Rejects one-way passive notifications. Deeply integrated with the Feishu Official WebSocket SDK (no public IP or NAT traversal required). Review AI-generated drafts on your phone, reply `发送` (Send) to execute real SMTP dispatch, or reply `修改: xxx` (Modify: xxx) to trigger AI rewriting on the fly.
* 🧠 **State Machine & MCP Extensibility:** Built on a rigorous directed acyclic graph (DAG) using LangGraph to eliminate infinite LLM loops. Features a built-in **Model Context Protocol (MCP)** array (running via `npx`), granting the LLM native abilities to read downloaded attachments (`./downloads`) and consult your local knowledge base (`./documents`).
* 🗄️ **Evolutionary Memory (Anti-Forgetting):** Uses LangMem and PostgreSQL/pgvector. Feedback sent via Feishu isn't just a one-off correction; the agent uses an "Extract & Append" LLM mechanism to dynamically update its permanent rulebook, ensuring it never forgets your personal tone and procedural preferences (Zero Prompt Drift).
* ⏰ **Smart Event Scheduling:** Automatically extracts meeting and event times from incoming emails. Powered by `APScheduler`, it sets up intelligent pre-warnings (e.g., 24 hours advance) and high-priority alerts (15 minutes before) pushed directly to your phone.

---

## 🛠️ Quick Start

### 1. Environment Setup

Ensure your system has **Python 3.10+** and **Node.js** (required for MCP `npx` commands). You will also need access to a PostgreSQL database for memory persistence.

Clone the repository and install the required dependencies:

```bash
git clone https://github.com/yourusername/MailGraph.git
cd MailGraph
python -m pip install -r requirements.txt

```

### 2. Feishu (Lark) Bot Preparation

1. Go to the [Feishu Developer Console](https://open.feishu.cn/app) and create a Custom App.
2. Enable the **Bot** feature and switch the Event Subscription method to **WebSocket**.
3. Add the `im.message.receive_v1` event and grant necessary messaging permissions.
4. Publish the app version to activate permissions.

### 3. Environment Variables Configuration

Copy the example environment file:

```bash
cp .env.example .env

```

Open the `.env` file and configure your specific credentials:

```env
# --- LLM & Database Configuration ---
DEEPSEEK_API_KEY="sk-xxxxxx"
DATABASE_URI="postgresql://user:password@host:port/dbname"

# --- Email Configuration (e.g., QQ Mail / Gmail) ---
IMAP_SERVER="imap.qq.com"
EMAIL_ACCOUNT="your_email@qq.com"
EMAIL_PASSWORD="your_app_password"
SMTP_HOST="smtp.qq.com"
SMTP_USER="your_email@qq.com"

# --- Feishu (Lark) WebSocket Configuration ---
FEISHU_APP_ID="cli_xxxxxx"
FEISHU_APP_SECRET="xxxxxx"
FEISHU_OWNER_OPEN_ID="ou_xxxxxx" # Your personal Open ID to receive alerts

```

*(Tip: You can find your `ou_` ID in the console logs by sending a test message to your bot after starting the script).*

### 4. Run the Agent

Once the setup is complete, launch your digital assistant:

```bash
python main.py

```

Watch the console as it boots up the multi-threaded architecture:

```text
============================================================
 Memory-Augmented AI Email Agent —— Native Intranet WS Edition
============================================================
[INFO] ⏰ Scheduler started
[INFO] 🔌 Booting MCP Extensibility Array...
[INFO] ✅ MCP node [Local_FileSystem] mounted -> 14 tools loaded
[INFO] 🚀 Core system ready. Mounting Feishu WebSocket channel...
[INFO] ✅ Connected to IMAP Server! Commencing Zero-Latency Monitoring...

```

You are now ready to manage your inbox entirely from your mobile chat window!
