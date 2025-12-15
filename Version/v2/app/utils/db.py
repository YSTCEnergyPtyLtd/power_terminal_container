import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from ..config import config
# 基础模型类
Base = declarative_base()

# 创建数据库引擎
engine = create_engine(
    config.SQLALCHEMY_DATABASE_URI,
    pool_size=20,
    max_overflow=30,
    pool_pre_ping=True,
    echo=False,
    connect_args={"charset": "utf8mb4"}
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 日志
log = logging.getLogger("pt.db")


def init_db():
    """初始化数据库（创建所有表）"""
    try:
        # 测试连接
        test_conn = engine.connect()
        test_conn.close()

        # 创建所有表
        Base.metadata.create_all(bind=engine)
        log.info(f"数据库表初始化完成：{config.DB_NAME}")
        return True
    except Exception as e:
        log.error(f"数据库初始化失败：{str(e)}")
        if "Access denied" in str(e):
            log.error("请检查数据库账号密码！")
        elif "Unknown database" in str(e):
            log.error(f"请先创建数据库：{config.DB_NAME}")
        return False


def get_db():
    """获取数据库会话（依赖注入用）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()