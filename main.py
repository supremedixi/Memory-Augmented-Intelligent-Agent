import os
import time
import email
import re
from email.header import decode_header
from imapclient import IMAPClient

from config import logger, store
from workflow import create_email_workflow, initialize_prompts

def parse_email_bytes(raw_email_bytes: bytes, email_id: str) -> dict:
    msg = email.message_from_bytes(raw_email_bytes)
    
    sub_tuple = decode_header(msg["Subject"])[0]
    subject = sub_tuple[0].decode(sub_tuple[1] or "utf-8", errors="ignore") if isinstance(sub_tuple[0], bytes) else sub_tuple[0]
    
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                body = part.get_payload(decode=True).decode(errors="ignore")
                break
            elif content_type == "text/html" and not body:
                html_content = part.get_payload(decode=True).decode(errors="ignore")
                body = re.sub(r'<[^>]+>', ' ', html_content)
    else:
        body = msg.get_payload(decode=True).decode(errors="ignore")
        if msg.get_content_type() == "text/html":
            body = re.sub(r'<[^>]+>', ' ', body)

    body = " ".join(body.split())

    return {
        "email_id": email_id,
        "author": msg.get("From", "unknown"),
        "subject": subject,
        "email_thread": body.strip()[:2000]
    }

def process_unread_emails(client: IMAPClient, agent, user_id: str):
    messages = client.search('UNSEEN')
    if not messages:
        return

    logger.info(f"📬 发现 {len(messages)} 封新邮件，开始处理...")
    
    # 批量拉取邮件内容
    fetch_data = client.fetch(messages, ['RFC822'])
    
    for msg_id, data in fetch_data.items():
        raw_email = data[b'RFC822']
        em_dict = parse_email_bytes(raw_email, str(msg_id))
        
        logger.info(f"⚡ 正在处理: {em_dict['subject']}")
        
        inputs = {"email_input": em_dict, "messages": [], "error_count": 0, "max_retries": 3}
        config = {"configurable": {"langgraph_user_id": user_id}}
        
        # 触发工作流
        for output in agent.stream(inputs, config=config):
            # 遍历图中每个节点的输出
            for node_name, state_update in output.items():
                if node_name == "triage":
                    res = state_update.get('triage_result')
                    logger.info(f" 大模型判定结果 -> [{res.upper()}]")
        
        client.set_flags(messages, [b'\\Seen'])

def main():
    print("=" * 60)
    print("  记忆增强邮件智能体 —— 24/7 IDLE 极速监听模式")
    print("=" * 60)

    IMAP_SERVER = os.getenv("IMAP_SERVER") 
    EMAIL_ACCOUNT = os.getenv("EMAIL_ACCOUNT")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

    if not all([IMAP_SERVER, EMAIL_ACCOUNT, EMAIL_PASSWORD]):
        logger.error("❌ 未配置 IMAP 环境变量，程序退出。")
        return

    user_id = "admin_user"
    initialize_prompts(user_id)
    agent = create_email_workflow()
    
    # 外层循环：负责在网络闪断时自动重连
    while True:
        try:
            # 建立加密连接
            with IMAPClient(IMAP_SERVER, ssl=True) as client:
                client.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
                client.select_folder('INBOX')
                logger.info(" 成功连接邮箱服务器！")
                
                # 第一步：先处理关机期间积累的未读邮件
                process_unread_emails(client, agent, user_id)
                
                logger.info("⏳ 进入 IDLE 长连接模式，毫秒级监听新邮件...")
                
                while True:
                    client.idle()
                    
                    # 监听 30 秒。如果有信件会瞬间打断（0延迟）；如果没有，30秒后自动往下走
                    responses = client.idle_check(timeout=30.0) 
                    
                    # 无论有没有收到信号，都必须先退出 IDLE 状态才能发其他指令
                    client.idle_done()
                    
                    if responses:
                        logger.info(f"👀 收到服务器信号: {responses}")
                        process_unread_emails(client, agent, user_id)
                        logger.info("💤 邮件处理完毕，重新进入潜行监听状态...")
                    else:
                        # 强制产生网络数据流动，告诉路由器和 QQ 服务器“我还活着，别掐我网线”
                        client.noop()
                        
                        # 顺便兜底检查一下，防止 QQ 邮箱漏推了通知
                        process_unread_emails(client, agent, user_id)
                        
        except KeyboardInterrupt:
            logger.info(" 收到退出指令，安全关机。")
            break
        except Exception as e:
            logger.warning(f" 连接断开或发生异常: {e}。10 秒后尝试重新连接...")
            time.sleep(10)

if __name__ == "__main__":
    main()
