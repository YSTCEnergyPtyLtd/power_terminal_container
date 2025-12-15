import os
import logging
from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from app.api import register_blueprints
from app.utils import init_db, STATE
from config import config


os.makedirs(config.DATA_DIR, exist_ok=True)
os.makedirs(config.LOG_DIR, exist_ok=True)
# 初始化日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(config.LOG_DIR, "power_terminal.log"), encoding="utf-8"),
        logging.StreamHandler()
    ]
)


# 创建应用
def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(config.BASE_DIR, "app/templates")
    )

    # 配置
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "flask-secret-key-123456")

    # 初始化数据库
    if init_db():
        STATE["db_status"] = "connected"
    else:
        STATE["db_status"] = "disconnected"

    # 配置限流
    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=["60 per minute"],
        storage_uri="memory://"
    )

    # 注册蓝图
    register_blueprints(app)

    # 创建数据/日志目录
    os.makedirs(config.DATA_DIR, exist_ok=True)
    os.makedirs(config.LOG_DIR, exist_ok=True)

    STATE["web_started"] = True
    return app