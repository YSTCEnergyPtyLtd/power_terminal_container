import threading
import logging
import time
from datetime import datetime
import pytz
from ..config import config  # 修正导入路径（避免跨包导入错误）

# 全局存储（非持久化，周期结束后清理）
STATE = {
    "loop_started": False,
    "last_cycle_start": None,
    "last_cycle_end": None,
    "last_error": None
}
DEVICE_DATA = {}  # {cycle_time: {serial_number: device_data}}
DEVICE_STRATEGIES = {}  # {cycle_time: {device_id: strategy}}
CYCLE_STATUS = {}  # {cycle_time: "running"/"completed"/"failed"}
STORAGE_LOCK = threading.Lock()  # 线程锁，保证数据安全

# 日志
log = logging.getLogger("pt.utils.cycle")

# 初始化周期基准时间（全局变量）
get_current_cycle_start_time = None


def get_current_cycle():
    """生成当前周期的时间标识（ISO格式）"""
    global get_current_cycle_start_time  # 声明修改全局变量
    AUS_TZ = pytz.timezone(config.TZ)

    # 核心修复：强制初始化基准时间（避免None）
    if get_current_cycle_start_time is None:
        get_current_cycle_start_time = time.time()
        log.warning("周期基准时间未初始化，自动补充初始化（当前时间戳）")

    # 计算当前周期起始时间戳
    cycle_interval = config.CYCLE_INTERVAL
    elapsed = time.time() - get_current_cycle_start_time
    cycle_index = int(elapsed // cycle_interval)
    cycle_start_ts = get_current_cycle_start_time + cycle_index * cycle_interval

    # 转为澳式时区的ISO格式
    cycle_start_dt = datetime.fromtimestamp(cycle_start_ts, tz=AUS_TZ)
    return cycle_start_dt.isoformat()


# 绑定基准时间到函数（兼容原有逻辑）
get_current_cycle.start_time = get_current_cycle_start_time


def is_upload_window_open(cycle_time):
    """判断当前周期的上传窗口是否开启"""
    cycle_start_ts = datetime.fromisoformat(cycle_time).timestamp()
    current_ts = time.time()
    return current_ts < (cycle_start_ts + config.UPLOAD_WINDOW)


def clean_expired_data():
    """清理过期周期数据（保留最近1个周期）"""
    with STORAGE_LOCK:
        current_cycle = get_current_cycle()
        expired_cycles = [ct for ct in DEVICE_DATA.keys() if ct != current_cycle]
        for ct in expired_cycles:
            if ct in DEVICE_DATA:
                del DEVICE_DATA[ct]
            if ct in DEVICE_STRATEGIES:
                del DEVICE_STRATEGIES[ct]
            if ct in CYCLE_STATUS:
                del CYCLE_STATUS[ct]
    log.info(f"清理过期周期数据，剩余有效周期：{list(DEVICE_DATA.keys())}")


def clean_cycle_data(cycle_time):
    """新增：清理指定周期的非持久化数据（周期结束后立即清理）"""
    with STORAGE_LOCK:
        # 删除当前周期设备数据
        if cycle_time in DEVICE_DATA:
            del DEVICE_DATA[cycle_time]
        # 删除当前周期策略数据
        if cycle_time in DEVICE_STRATEGIES:
            del DEVICE_STRATEGIES[cycle_time]
        # 标记周期状态为已清理
        if cycle_time in CYCLE_STATUS:
            del CYCLE_STATUS[cycle_time]
    log.info(f"周期{cycle_time}非持久化数据已清理")