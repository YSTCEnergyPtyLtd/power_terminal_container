from datetime import datetime
import pytz
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from ..config import config
from app.utils.db import Base
AUS_TZ = pytz.timezone(config.TZ)

class YstcUser(Base):
    __tablename__ = "ystc_user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, comment="用户名（唯一）")
    password_hash = Column(String(128), nullable=False, comment="密码哈希")
    name = Column(String(50), nullable=False, comment="用户姓名")
    phone = Column(String(20), nullable=True, comment="电话号码")
    email = Column(String(100), nullable=True, comment="邮箱")
    address = Column(String(200), nullable=True, comment="物理地址")
    powerline_info = Column(String(200), nullable=True, comment="电线母线信息")
    is_active = Column(Boolean, default=True, nullable=False, comment="是否激活")
    last_login = Column(DateTime, nullable=True, comment="最后登录时间")
    create_by = Column(String(50), nullable=False, comment="创建人")
    create_time = Column(DateTime, default=lambda: datetime.now(AUS_TZ), nullable=False, comment="创建时间")
    update_by = Column(String(50), nullable=True, comment="更新人")
    update_time = Column(DateTime, onupdate=lambda: datetime.now(AUS_TZ), nullable=True, comment="更新时间")