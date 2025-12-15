from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON, Float, Boolean
from app.utils.db import Base
from datetime import datetime
import pytz
from app.config import config

AUS_TZ = pytz.timezone(config.TZ)

class GameStrategy(Base):
    __tablename__ = "ystc_game_strategy"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("ystc_user.id"), nullable=False, comment="所属用户ID")
    strategy_name = Column(String(100), default="cycle_strategy", comment="策略名称")
    strategy_type = Column(String(30), default="game_theory", comment="策略类型")
    algorithm_version = Column(String(20), default="1.0", comment="算法版本")
    start_time = Column(DateTime, nullable=False, comment="策略开始时间")
    end_time = Column(DateTime, nullable=False, comment="策略结束时间")
    time_slices = Column(Integer, default=config.TIME_SLOTS, comment="时间片数量")
    time_slice_interval = Column(Float, nullable=False, comment="时间片间隔（秒）")  
    strategy_params = Column(JSON, nullable=True, comment="策略参数")  
    strategy_json = Column(JSON, nullable=False, comment="完整策略JSON")
    external_conditions = Column(String(200), nullable=True, comment="外部条件")  
    is_active = Column(Boolean, default=True, comment="是否激活")  
    status = Column(String(20), default="completed", comment="策略状态")
    create_by = Column(String(50), nullable=False, comment="创建人")  
    create_time = Column(DateTime, default=lambda: datetime.now(AUS_TZ), comment="创建时间")
    update_by = Column(String(50), nullable=True, comment="更新人")  
    update_time = Column(DateTime, onupdate=lambda: datetime.now(AUS_TZ), comment="更新时间")  

class StrategyDetail(Base):
    __tablename__ = "ystc_strategy_detail"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, ForeignKey("ystc_game_strategy.id"), nullable=False, comment="关联策略主表")
    time_slice_index = Column(Integer, nullable=False, comment="时间片索引（0/1/2）")
    time_point = Column(DateTime, nullable=False, comment="时间点")
    action_type = Column(String(20), nullable=False, comment="动作类型（charge/discharge/idle）")
    power_setpoint = Column(Float, nullable=False, comment="功率设定点")
    expected_price = Column(Float, nullable=True, comment="预期电价")
    expected_benefit = Column(Float, nullable=True, comment="该时间片预期收益")
    create_by = Column(String(50), nullable=False, comment="创建人")  
    create_time = Column(DateTime, default=lambda: datetime.now(AUS_TZ), comment="创建时间")
    update_by = Column(String(50), nullable=True, comment="更新人")  
    update_time = Column(DateTime, onupdate=lambda: datetime.now(AUS_TZ), comment="更新时间")  

class ControlCommand(Base):
    __tablename__ = "ystc_control_command"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(Integer, ForeignKey("ystc_device.id"), nullable=False, comment="目标设备ID")
    strategy_id = Column(Integer, ForeignKey("ystc_game_strategy.id"), nullable=False, comment="关联策略ID")
    command_type = Column(String(30), nullable=False, comment="命令类型（strategy_exec）")
    command_params = Column(JSON, nullable=False, comment="命令参数（策略详情）")
    priority = Column(Integer, default=1, comment="命令优先级")  
    issued_at = Column(DateTime, default=lambda: datetime.now(AUS_TZ), comment="下发时间")
    scheduled_at = Column(DateTime, nullable=False, comment="计划执行时间")  
    expire_at = Column(DateTime, nullable=False, comment="命令过期时间")  
    executed_at = Column(DateTime, nullable=True, comment="执行时间")
    status = Column(String(20), default="pending", comment="命令状态（pending/executed/failed）")
    result = Column(String(50), nullable=True, comment="执行结果（success/fail）")  
    error_message = Column(String(200), nullable=True, comment="错误信息")  
    retry_count = Column(Integer, default=0, comment="重试次数")  
    max_retries = Column(Integer, default=3, comment="最大重试次数")  
    create_by = Column(String(50), nullable=False, comment="创建人")  
    create_time = Column(DateTime, default=lambda: datetime.now(AUS_TZ), comment="创建时间")
    update_by = Column(String(50), nullable=True, comment="更新人")  
    update_time = Column(DateTime, onupdate=lambda: datetime.now(AUS_TZ), comment="更新时间")