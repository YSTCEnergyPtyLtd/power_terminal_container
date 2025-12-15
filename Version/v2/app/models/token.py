from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean
from app.utils.db import Base
from datetime import datetime, timedelta
import pytz
from app.config import config

AUS_TZ = pytz.timezone(config.TZ)

class UserAuthToken(Base):
    __tablename__ = "ystc_user_auth_token"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("ystc_user.id"), nullable=False, comment="关联用户ID")
    token_hash = Column(String(256), nullable=False, comment="token哈希")
    refresh_token_hash = Column(String(256), nullable=False, comment="刷新token哈希")
    expires_at = Column(DateTime, default=lambda: datetime.now(AUS_TZ) + timedelta(days=365 * 100), nullable=False,
                        comment="过期时间")
    refresh_expires_at = Column(DateTime, default=lambda: datetime.now(AUS_TZ) + timedelta(days=365 * 100),
                                nullable=False, comment="刷新token过期时间")
    client_info = Column(String(200), nullable=True, comment="客户端信息")
    is_valid = Column(Boolean, default=True, comment="是否有效（logout时设为False）")
    last_used_at = Column(DateTime, nullable=True, comment="最后使用时间")
    create_by = Column(String(50), nullable=False, comment="创建人")
    create_time = Column(DateTime, default=lambda: datetime.now(AUS_TZ), comment="创建时间")
    update_by = Column(String(50), nullable=True, comment="更新人")
    update_time = Column(DateTime, onupdate=lambda: datetime.now(AUS_TZ), comment="更新时间")