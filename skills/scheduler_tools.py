import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from utils.feishu_api import send_feishu_message

logger = logging.getLogger("EmailAgent")

# 初始化持久化调度器 (任务存在本地 schedule.db 文件中)
jobstores = {
    'default': SQLAlchemyJobStore(url='sqlite:///schedule.db')
}
scheduler = AsyncIOScheduler(jobstores=jobstores)

def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        logger.info("⏰ 定时任务调度器已启动")

def schedule_event_reminder(event_title: str, event_time_str: str, author: str):
    try:
        event_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()

        if event_time < now:
            logger.info(f"事件 [{event_title}] 时间已过，跳过定时。")
            return

        # ================= 1. 设定提前 24 小时提醒 (中长期预警) =================
        advance_1d = event_time - timedelta(days=1)
        
        # 如果距离事件发生还有 24 小时以上，才添加这个明日预警
        if advance_1d > now:
            scheduler.add_job(
                send_feishu_message,
                'date',
                run_date=advance_1d,
                args=[f"⏳ [明日预警] {event_title}", f"**发件人:** {author}\n\n该事件将于 **明天** ({event_time_str}) 发生，请提前做好准备！"],
                id=f"advance_1d_{event_title}_{event_time_str}", 
                replace_existing=True
            )
            logger.info(f"📅 已设置提前24小时提醒: {advance_1d}")

        # ================= 2. 设定临近开始前的高优提醒 (如：提前 15 分钟) =================
        # 如果你想改成提前 1 小时，就改为 timedelta(hours=1)
        # 如果你想改成提前 10 分钟，就改为 timedelta(minutes=10)
        advance_15m = event_time - timedelta(minutes=15)
        
        # 校验：只有当前时间还没到“提前 15 分钟”的节点，才加入定时器
        if advance_15m > now:
            scheduler.add_job(
                send_feishu_message,
                'date',
                run_date=advance_15m,
                args=[f"🔔 [即将开始] {event_title}", f"**发件人:** {author}\n\n该事件将在 **15分钟后** ({event_time_str}) 开始，请停下手中的工作准备接入！"],
                id=f"advance_15m_{event_title}_{event_time_str}",
                replace_existing=True
            )
            logger.info(f"📅 已设置提前15分钟高优提醒: {advance_15m}")
        else:
            logger.info(f"距 [{event_title}] 发生已不足预设的提前时间，跳过临近提醒设定。")

    except Exception as e:
        logger.error(f"解析时间或添加定时任务失败: {e}")