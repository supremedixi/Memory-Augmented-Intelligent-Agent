import os
import json
import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
from config import logger

# 官方 SDK Client：它会在底层自动帮你获取并刷新 tenant_access_token！
lark_client = lark.Client.builder() \
    .app_id(os.getenv("FEISHU_APP_ID", "")) \
    .app_secret(os.getenv("FEISHU_APP_SECRET", "")) \
    .log_level(lark.LogLevel.WARNING) \
    .build()

def send_feishu_message(title: str, content: str, open_id: str = None):
    """
    使用官方 SDK 主动发送飞书富文本消息
    :param title: 卡片标题
    :param content: 卡片正文
    :param open_id: 指定发给谁，为空则发给 FEISHU_OWNER_OPEN_ID
    """
    target_id = open_id or os.getenv("FEISHU_OWNER_OPEN_ID")
    if not target_id:
        logger.warning("未配置 FEISHU_OWNER_OPEN_ID，跳过发送飞书消息。")
        return

    msg_content = {
        "zh_cn": {
            "title": title,
            "content": [
                [{"tag": "text", "text": content}],
                [{"tag": "text", "text": "\n\n快捷指令回复:\n- 回复【发送】立即执行发送\n- 回复【修改：xxx】让智能体优化指令并重写草稿"}]
            ]
        }
    }

    request = CreateMessageRequest.builder() \
        .receive_id_type("open_id") \
        .request_body(CreateMessageRequestBody.builder()
            .receive_id(target_id)
            .msg_type("post")
            .content(json.dumps(msg_content))
            .build()) \
        .build()

    try:
        response = lark_client.im.v1.message.create(request)
        if response.success():
            logger.info(f"飞书推送成功: {title}")
        else:
            logger.warning(f"飞书推送失败, 错误码: {response.code}, 信息: {response.msg}")
    except Exception as e:
        logger.error(f"发送飞书消息发生底层异常: {e}")
