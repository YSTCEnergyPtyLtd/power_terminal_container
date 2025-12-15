import logging
import asyncio
import threading
from flask import Flask
from app.api.auth import auth_bp
from app.api.device import device_bp
from app.core.cycle_manager import service_loop
from app.utils.db import init_db
from config import config

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("power_terminal.log", encoding="utf-8")
    ]
)
log = logging.getLogger("pt.main")

# Flask应用初始化
app = Flask(__name__)
app.config.from_object(config)

# 初始化数据库（首次运行自动创建表）
init_db()
log.info("数据库表初始化完成：ystc")

# 蓝图注册
# 认证页面路由（login/dashboard）
app.register_blueprint(auth_bp)
# 设备API接口：保留/api/device前缀，接口路径如 /api/device/upload
app.register_blueprint(device_bp, url_prefix="/api/device")

# 周期后台服务启动
# 避免周期服务重复启动
cycle_service_started = False

def start_cycle_service():
    """异步启动周期循环服务（守护线程）"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(service_loop())
    except Exception as e:
        log.error(f"周期服务异常退出：{str(e)}", exc_info=True)
    finally:
        loop.close()

@app.before_request
def init_background_tasks():
    global cycle_service_started
    if not cycle_service_started:
        log.info("启动周期后台服务...")
        # 启动周期服务线程（守护线程，随主进程退出）
        cycle_thread = threading.Thread(target=start_cycle_service, daemon=True)
        cycle_thread.start()
        # 标记已启动，防止重复执行
        cycle_service_started = True

# 主入口
if __name__ == "__main__":
    log.info("启动Power Terminal服务...")
    # 启动Flask Web服务（禁用debug/reloader避免周期服务重复启动）
    app.run(
        host="0.0.0.0",
        port=8080,
        debug=False,  # 生产环境保持False
        use_reloader=False  # 关闭自动重载，避免周期服务启动两次
    )