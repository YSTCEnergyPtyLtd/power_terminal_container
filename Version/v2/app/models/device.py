from datetime import datetime
import pytz
from app.utils.db import Base
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey
from ..config import config

AUS_TZ = pytz.timezone(config.TZ)


class Device(Base):
    __tablename__ = "ystc_device"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(30), nullable=False, comment="设备类型（电池/逆变器/电表）")
    model = Column(String(50), nullable=True, comment="设备型号")
    firmware_version = Column(String(20), nullable=True, comment="固件版本")
    serial_number = Column(String(50), unique=True, nullable=False, comment="设备序列号（唯一）")
    working_power = Column(Float, nullable=True, comment="工况功率")  
    address = Column(String(50), nullable=True, comment="通信地址")  
    port = Column(Integer, nullable=True, comment="通信端口")  
    baudrate = Column(Integer, nullable=True, comment="波特率")  
    addr = Column(String(20), nullable=True, comment="设备地址")  
    status = Column(String(20), default="offline", nullable=False, comment="设备状态（online/offline）")
    last_online = Column(DateTime, nullable=True, comment="最后在线时间")
    last_communication = Column(DateTime, nullable=True, comment="最后通信时间")  
    user_id = Column(Integer, ForeignKey("ystc_user.id"), nullable=False, comment="所属用户ID（关联账号）")
    location = Column(String(200), nullable=True, comment="安装位置")
    is_active = Column(Boolean, default=True, nullable=False, comment="是否激活")  
    notes = Column(String(200), nullable=True, comment="备注")  
    create_by = Column(String(50), nullable=False, comment="创建人")  
    create_time = Column(DateTime, default=lambda: datetime.now(AUS_TZ), nullable=False, comment="注册时间")
    update_by = Column(String(50), nullable=True, comment="更新人")  
    update_time = Column(DateTime, onupdate=lambda: datetime.now(AUS_TZ), nullable=True, comment="更新时间")