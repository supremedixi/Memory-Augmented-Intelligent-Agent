import os
import time
import asyncio
import threading
from imapclient import IMAPClient

from config import logger
from workflow import create_email_workflow, initialize_prompts
from skills.scheduler_tools import start_scheduler
from skills.mcp_connector import MultiMCPManager
from bot_server import start_feishu_websocket 

def parse_email_bytes(raw_email_bytes: bytes, email_id: str) -> dict:
    import email
    import re
    from email.header import decode_header
    msg = email.message_from_bytes(raw_email_bytes)
    
    sub_tuple = decode_header(msg["Subject"])[0]
    subject = sub_tuple[0].decode(sub_tuple[1] or "utf-8", errors="ignore") if isinstance(sub_tuple[0], bytes) else sub_tuple[0]
    
    body = ""
    saved_attachments = []
    
    download_dir = "./downloads"
    os.makedirs(download_dir, exist_ok=True)

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))

            if "attachment" not in content_disposition:
                if content_type == "text/plain":
                    body = part.get_payload(decode=True).decode(errors="ignore")
                elif content_type == "text/html" and not body:
                    html_content = part.get_payload(decode=True).decode(errors="ignore")
                    body = re.sub(r'<[^>]+>', ' ', html_content)
            
            if "attachment" in content_disposition:
                filename = part.get_filename()
                if filename:
                    fn_tuple = decode_header(filename)[0]
                    decoded_filename = fn_tuple[0].decode(fn_tuple[1] or "utf-8", errors="ignore") if isinstance(fn_tuple[0], bytes) else fn_tuple[0]
                    filepath = os.path.join(download_dir, f"{email_id}_{decoded_filename}")
                    with open(filepath, "wb") as f:
                        f.write(part.get_payload(decode=True))
                    saved_attachments.append(filepath)
    else:
        body = msg.get_payload(decode=True).decode(errors="ignore")
        if msg.get_content_type() == "text/html":
            body = re.sub(r'<[^>]+>', ' ', body)

    body = " ".join(body.split())

    return {
        "email_id": email_id,
        "author": msg.get("From", "unknown"),
        "subject": subject,
        "email_thread": body.strip()[:2000],
        "attachments": saved_attachments 
    }

async def _run_agent_workflow_async(em_dict: dict, user_id: str):
    inputs = {"email_input": em_dict, "messages": [], "error_count": 0, "max_retries": 3}
    config = {"configurable": {"langgraph_user_id": user_id}}
    
    async for output in global_agent.astream(inputs, config=config):
        for node_name, state_update in output.items():
            if node_name == "triage":
                res = state_update.get('triage_result')
                logger.info(f" 大模型判定结果 -> [{res.upper()}]")

def process_unread_emails(client: IMAPClient, user_id: str):
    messages = client.search('UNSEEN')
    if not messages:
        return

    logger.info(f" 发现 {len(messages)} 封新邮件，开始处理...")
    fetch_data = client.fetch(messages, ['RFC822'])
    
    for msg_id, data in fetch_data.items():
        raw_email = data[b'RFC822']
        em_dict = parse_email_bytes(raw_email, str(msg_id))
        logger.info(f" 正在处理: {em_dict['subject']}")
        
        future = asyncio.run_coroutine_threadsafe(_run_agent_workflow_async(em_dict, user_id), main_loop)
        future.result() 
        
    client.set_flags(messages, [b'\\Seen'])


def imap_listener_thread(user_id: str):
    """【子线程 1】专门负责 IMAP 协议长连接"""
    IMAP_SERVER = os.getenv("IMAP_SERVER") 
    EMAIL_ACCOUNT = os.getenv("EMAIL_ACCOUNT")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

    while True:
        try:
            with IMAPClient(IMAP_SERVER, ssl=True) as client:
                client.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
                client.select_folder('INBOX')
                logger.info("成功连接邮箱服务器！开始极速监听模式...")
                
                process_unread_emails(client, user_id)
                
                while True:
                    client.idle()
                    responses = client.idle_check(timeout=30.0) 
                    client.idle_done()
                    if responses:
                        process_unread_emails(client, user_id)
                    else:
                        client.noop()
                        process_unread_emails(client, user_id)
                        
        except Exception as e:
            logger.warning(f" IMAP 异常: {e}。10 秒后重连...")
            time.sleep(10)

def feishu_listener_thread():
    """【子线程 2】专门运行阻塞的飞书 WebSocket 长连接"""
    try:
        start_feishu_websocket()
    except Exception as e:
        logger.error(f"飞书长连接线程异常: {e}")

async def async_main():
    """【主线程】维护唯一的 Asyncio 事件循环，守护 MCP 连接"""
    global main_loop, global_agent
    main_loop = asyncio.get_running_loop()
    
    print("=" * 60)
    print(" 记忆增强邮件智能体 —— 纯内网长连接版")
    print("=" * 60)
    start_scheduler()
    
    user_id = "admin_user"
    initialize_prompts(user_id)
    
    mcp_manager = MultiMCPManager()
    
    try:
        mcp_tools = await mcp_manager.initialize()
        global_agent = create_email_workflow(mcp_tools)

        t1 = threading.Thread(target=imap_listener_thread, args=(user_id,), daemon=True)
        t1.start()
        
        logger.info("核心系统就绪。正在挂载飞书官方长连接通道...")
        t2 = threading.Thread(target=feishu_listener_thread, daemon=True)
        t2.start()
        
        while True:
            await asyncio.sleep(3600)
            
    except asyncio.CancelledError:
        logger.info(" 接收到关闭信号...")
    finally:
        await mcp_manager.cleanup()

if __name__ == "__main__":
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n 程序已安全退出。")
