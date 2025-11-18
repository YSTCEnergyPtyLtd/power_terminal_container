# config.py
import os
from dotenv import load_dotenv

# 加载.env文件（本地开发用）：如果.env存在，优先读取里面的配置；不存在则读取系统环境变量
load_dotenv()  # 自动查找项目根目录的.env文件，加载到环境变量中


class Config:
    """配置类：统一管理所有配置，优先读取系统环境变量，其次读.env文件，最后用默认值"""
    # 数据库配置（核心）
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")  # 默认值127.0.0.1
    DB_PORT = os.getenv("DB_PORT", "3306")  # 默认值3306
    DB_USER = os.getenv("DB_USER", "root")  # 默认值root
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")  # 密码无默认值，须配置
    DB_NAME = os.getenv("DB_NAME", "")  # 数据库名

    # 拼接数据库连接URL（使用SQLAlchemy）
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )

    # 其他原有配置（从.env或环境变量读取）
    TZ = os.getenv("TZ", "Australia/Melbourne")
    DATA_DIR = os.getenv("DATA_DIR", "/app/data")
    LOG_DIR = os.getenv("LOG_DIR", "/app/logs")


# 创建配置实例，供其他文件导入
config = Config()