import os
import smtplib
import imaplib
import traceback
import time
from functools import wraps
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from langchain_core.tools import tool
from langmem import create_manage_memory_tool, create_search_memory_tool

from config import logger

def safe_tool(func):
    """工具异常拦截装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        tool_name = func.__name__
        try:
            logger.debug(f"🔧 调用工具 [{tool_name}]")
            result = func(*args, **kwargs)
            logger.info(f"✅ 工具 [{tool_name}] 执行成功")
            return result
        except Exception as e:
            error_msg = f"❌ 工具 [{tool_name}] 执行失败: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            return f"工具调用失败: {str(e)}。请告知用户。"
    return wrapper

@tool
@safe_tool
def write_email(to: str, subject: str, content: str, cc: str = "", draft_only: bool = False) -> str:
    """撰写并发送真实邮件（或直接同步到云端草稿箱）"""
    
    smtp_user = os.getenv("SMTP_USER", "")
    if not smtp_user:
        return "⚠️ 环境变量未配置 SMTP_USER，无法操作邮件。"

    # 1. 无论发送还是存草稿，都必须先构建邮件的底层结构
    msg = MIMEMultipart("alternative")
    msg["From"] = smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    if cc: 
        msg["Cc"] = cc
    msg.attach(MIMEText(content, "plain", "utf-8"))
    
    # 转换为字节流，这是 IMAP 上传所需的格式
    raw_msg_bytes = msg.as_bytes()

    # ================= 分支 A：仅保存到草稿箱 =================
    if draft_only:
        imap_server = os.getenv("IMAP_SERVER", "imap.qq.com")
        email_account = os.getenv("EMAIL_ACCOUNT", smtp_user)
        email_password = os.getenv("EMAIL_PASSWORD", "")
        
        if not email_password:
            return "⚠️ 未配置 EMAIL_PASSWORD，无法连接服务器保存草稿。"
            
        try:
            # 连接 IMAP 服务器
            mail = imaplib.IMAP4_SSL(imap_server)
            mail.login(email_account, email_password)
            
            # 使用 append 指令将邮件字节流上传到 "Drafts" (草稿箱)
            # imaplib.Time2Internaldate(time.time()) 会打上当前的时间戳
            mail.append("Drafts", '', imaplib.Time2Internaldate(time.time()), raw_msg_bytes)
            mail.logout()
            
            logger.info(f"💾 草稿已成功同步至邮箱: 主题='{subject}'")
            return f"✅ 草稿已成功存入您的邮箱【草稿箱】。收件人: {to}, 主题: '{subject}'"
        except Exception as e:
            logger.error(f"存入草稿箱失败: {e}")
            return f"⚠️ 智能体草稿生成成功，但同步到邮箱服务器失败: {e}。内容已保留在内存中。"

    # ================= 分支 B：真实发送邮件 =================
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    smtp_password = os.getenv("SMTP_PASSWORD", "")

    if not smtp_host or not smtp_password:
        return "⚠️ SMTP 未完全配置，邮件未实际发送。"

    # 使用 SSL 协议发送（主流邮箱如 QQ/网易 必需）
    with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
        server.login(smtp_user, smtp_password)
        all_recipients = [to] + [c.strip() for c in cc.split(",") if c.strip()]
        server.sendmail(smtp_user, all_recipients, msg.as_string())

    logger.info(f"📨 邮件已真实发送: to={to}, subject='{subject}'")
    return f"✅ 邮件已成功发送 -> 收件人: {to}, 主题: '{subject}'"

# 记忆工具组装
manage_memory_tool = create_manage_memory_tool(namespace=("email_assistant", "{langgraph_user_id}", "collection"))
search_memory_tool = create_search_memory_tool(namespace=("email_assistant", "{langgraph_user_id}", "collection"))

tools_list = [write_email, manage_memory_tool, search_memory_tool]