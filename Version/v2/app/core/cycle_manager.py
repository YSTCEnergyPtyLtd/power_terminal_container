import logging
import time
import asyncio
from datetime import datetime
import pytz
from app.core.jar_executor import call_jar_model
from app.utils import (
    STATE, DEVICE_DATA, STORAGE_LOCK,
    get_current_cycle, clean_expired_data, clean_cycle_data, SessionLocal
)
from app.models import Device
from ..config import config

log = logging.getLogger("pt.cycle")
AUS_TZ = pytz.timezone(config.TZ)

# 绑定周期基准时间（初始化）
get_current_cycle.start_time = None
# 周期执行锁，防止同一个周期重复执行
EXECUTED_CYCLES = set()  # 记录已执行的周期
IS_LOOP_RUNNING = False  # 标记循环是否已启动


async def run_cycle(cycle_time):
    """执行单个周期逻辑（增加防重复执行）"""
    # 1. 防重复执行：同一个周期只执行一次
    if cycle_time in EXECUTED_CYCLES:
        log.warning(f"周期{cycle_time}已执行过，跳过重复执行")
        return
    EXECUTED_CYCLES.add(cycle_time)

    STATE["last_cycle_start"] = datetime.now(AUS_TZ).isoformat()
    log.info(f"\n=== 周期启动：{cycle_time} ===")

    try:
        # 检查当前周期是否有设备上传数据
        with STORAGE_LOCK:
            has_device_data = bool(DEVICE_DATA.get(cycle_time, {}))

        # 无设备数据 就直接跳过博弈+清理
        if not has_device_data:
            log.warning(f"周期{cycle_time}无设备上传数据，跳过博弈计算")
            STATE["last_cycle_end"] = datetime.now(AUS_TZ).isoformat()
            log.info(f"=== 周期结束：{cycle_time}（无数据）===")
            clean_cycle_data(cycle_time)  # 清理空数据
            EXECUTED_CYCLES.discard(cycle_time)  # 移除标记，避免影响后续
            return

        # 有设备数据 就调用JAR博弈
        await call_jar_model(cycle_time)

        # 博弈完成后 清理当前周期数据
        clean_cycle_data(cycle_time)

        STATE["last_cycle_end"] = datetime.now(AUS_TZ).isoformat()
        log.info(f"=== 周期结束：{cycle_time}（数据已清理）===")
        EXECUTED_CYCLES.discard(cycle_time)  # 执行完成后移除标记

    except Exception as e:
        log.error(f"周期{cycle_time}执行异常", exc_info=True)
        STATE["last_error"] = repr(e)
        clean_cycle_data(cycle_time)  # 异常时清理数据
        STATE["last_cycle_end"] = datetime.now(AUS_TZ).isoformat()
        EXECUTED_CYCLES.discard(cycle_time)  # 异常后移除标记


async def service_loop():
    """后台周期循环主逻辑（增加防重复启动）"""
    global IS_LOOP_RUNNING
    # 防重复启动：如果已有循环在运行，直接返回
    if IS_LOOP_RUNNING:
        log.warning("周期循环服务已启动，跳过重复启动")
        return
    IS_LOOP_RUNNING = True

    try:
        STATE["loop_started"] = True
        log.info("周期循环服务启动")

        # 等待至少有一个设备注册
        db = SessionLocal()
        while not db.query(Device).first():
            db.close()
            await asyncio.sleep(5)
            db = SessionLocal()
        db.close()
        log.info("检测到已注册设备，启动周期循环")

        # 初始化周期起始时间
        current_start_time = time.time()
        get_current_cycle.start_time = current_start_time

        # 正确修改全局周期起始时间
        import app.utils.cycle as cycle_module
        if hasattr(cycle_module, "get_current_cycle_start_time"):
            cycle_module.get_current_cycle_start_time = current_start_time
        log.info(f"周期基准时间：{datetime.fromtimestamp(current_start_time, tz=AUS_TZ)}")

        # 主循环
        while IS_LOOP_RUNNING:  # 用标记控制循环退出
            current_cycle = get_current_cycle()  # 此时基准时间已初始化
            cycle_start_ts = datetime.fromisoformat(current_cycle).timestamp()

            # 等待上传窗口关闭
            upload_deadline = cycle_start_ts + config.UPLOAD_WINDOW
            current_ts = time.time()
            if current_ts < upload_deadline:
                wait_time = upload_deadline - current_ts
                log.info(f"周期{current_cycle}上传窗口开启，剩余{wait_time:.1f}秒")
                await asyncio.sleep(wait_time)

            # 执行周期逻辑
            await run_cycle(current_cycle)

            # 清理过期数据
            clean_expired_data()

            # 等待下一个周期
            next_cycle_ts = cycle_start_ts + config.CYCLE_INTERVAL
            current_ts = time.time()
            if current_ts < next_cycle_ts:
                wait_time = next_cycle_ts - current_ts
                log.info(f"等待{wait_time:.1f}秒进入下一个周期")
                await asyncio.sleep(wait_time)

    except Exception as e:
        STATE["last_error"] = repr(e)
        log.exception("周期循环异常")
        IS_LOOP_RUNNING = False  # 异常时重置标记
        # 异常后重启周期服务
        await asyncio.sleep(10)
        await service_loop()


# 安全启动周期服务
async def start_cycle_service():
    """安全启动周期服务，确保只启动一次"""
    global IS_LOOP_RUNNING
    if not IS_LOOP_RUNNING:
        asyncio.create_task(service_loop())
    else:
        log.warning("周期服务已在运行，无需重复启动")