import json
import re
import logging
import subprocess
import asyncio
from datetime import datetime, timedelta
import pytz
from app.utils import (
    DEVICE_DATA, DEVICE_STRATEGIES, CYCLE_STATUS, STORAGE_LOCK,
    SessionLocal
)
from app.models import (
    GameStrategy, StrategyDetail, ControlCommand, Device, YstcUser
)
from ..config import config

log = logging.getLogger("pt.jar")
AUS_TZ = pytz.timezone(config.TZ)


# 创建数据库连接池复用
async def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def call_jar_model(cycle_time):
    """调用JAR模型（修复produce字段+ID校验）"""
    # 校验JAR文件存在性
    JAR_PATH = "game-model-1.0.jar"
    if not __import__("os").path.exists(JAR_PATH):
        log.error(f"JAR文件不存在：{JAR_PATH}")
        with STORAGE_LOCK:
            CYCLE_STATUS[cycle_time] = "failed"
        return None

    # 提取当前周期设备数据
    with STORAGE_LOCK:
        current_devices = DEVICE_DATA.get(cycle_time, {})  # {serial_number: device_data}
    if not current_devices:
        log.warning(f"周期{cycle_time}无设备数据，跳过博弈")
        with STORAGE_LOCK:
            CYCLE_STATUS[cycle_time] = "completed"
        return None

    # 关联设备 用户+构建纯净设备列表
    db = SessionLocal()
    new_id_original_id_map = {}  # {新ID: 原device.id}
    original_id_serial_map = {}  # 存储数据库Device ID
    serial_user_map = {}  # {serial_number: user_id}
    processed_devices = []

    try:
        for idx, (serial_num, device_data) in enumerate(current_devices.items()):
            # 验证device_data必须有id
            if "id" not in device_data or not isinstance(device_data["id"], (int, str)):
                log.warning(f"设备{serial_num}缺失有效id，跳过")
                continue

            # 关联设备→用户ID + 数据库Device主键ID
            device_db = db.query(Device).filter_by(serial_number=serial_num).first()
            if not device_db or not device_db.user_id:
                log.warning(f"设备{serial_num}未关联用户，跳过")
                continue
            serial_user_map[serial_num] = device_db.user_id
            # 核心修改：存储「原ID→(序列号, 数据库Device主键ID)」
            original_id_serial_map[device_data["id"]] = (serial_num, device_db.id)

            # 重置ID为0开始的连续索引
            new_device_id = idx  # 新ID从0开始
            new_id_original_id_map[new_device_id] = device_data["id"]  # 新ID→原ID 构造映射

            # 构建纯净设备数据（使用新的ID）
            clean_device = {
                "id": new_device_id,  # 使用新ID（从0开始）
                "produce": device_data.get("produce", []),
                "chargeCost": device_data.get("chargeCost", []),
                "currentStorage": device_data.get("currentStorage", []),
                "chargeSpeed": device_data.get("chargeSpeed", []),
                "dischargeSpeed": device_data.get("dischargeSpeed", []),
                "overallCapacity": device_data.get("overallCapacity", 0.0),
                "demands": device_data.get("demands", []),
                "dischargeCost": device_data.get("dischargeCost", [])
            }

            # 修复produce字段：强制补全为长度3的数组（不跳过设备）
            if clean_device["produce"] is None:
                clean_device["produce"] = [0.0] * config.TIME_SLOTS
            elif not isinstance(clean_device["produce"], list):
                clean_device["produce"] = [0.0] * config.TIME_SLOTS
            else:
                # 长度不足补0，过长截断
                if len(clean_device["produce"]) < config.TIME_SLOTS:
                    clean_device["produce"] += [0.0] * (config.TIME_SLOTS - len(clean_device["produce"]))
                elif len(clean_device["produce"]) > config.TIME_SLOTS:
                    clean_device["produce"] = clean_device["produce"][:config.TIME_SLOTS]

            # 日志仅提示，不跳过设备
            if len(clean_device["produce"]) != config.TIME_SLOTS:
                log.warning(f"设备原ID={device_data['id']}的produce字段已强制补全为长度{config.TIME_SLOTS}的数组")

            processed_devices.append(clean_device)
            log.debug(f"设备映射：新ID={new_device_id} → 原ID={device_data['id']} → 序列号={serial_num} → 数据库Device ID={device_db.id}")
    finally:
        db.close()

    # 无有效设备数据 → 标记完成
    if not processed_devices:
        log.warning(f"周期{cycle_time}无有效设备数据，跳过博弈")
        with STORAGE_LOCK:
            CYCLE_STATUS[cycle_time] = "completed"
        return None

    # 调用JAR
    devices_json = json.dumps(processed_devices, ensure_ascii=False)
    log.info(
        f"JAR输入：设备数={len(processed_devices)}，新ID范围0-{len(processed_devices) - 1}，用户数={len(set(serial_user_map.values()))}")

    try:
        # 异步调用JAR
        result = await asyncio.to_thread(
            subprocess.run,
            ["java", "-jar", JAR_PATH, devices_json],
            capture_output=True,
            text=True,
            timeout=30
        )

        # 处理JAR输出
        if result.returncode != 0:
            log.error(f"JAR执行失败：\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
            with STORAGE_LOCK:
                CYCLE_STATUS[cycle_time] = "failed"
            return None

        # 提取JSON结果
        json_match = re.search(r'\{[\s\S]*\}', result.stdout, re.DOTALL)
        if not json_match:
            log.error(f"JAR输出无JSON：{result.stdout}")
            with STORAGE_LOCK:
                CYCLE_STATUS[cycle_time] = "failed"
            return None

        java_result = json.loads(json_match.group())
        full_result = java_result.get("full_result", java_result)
        decisions = full_result.get("decisions", [])
        log.info(f"JAR博弈完成：生成{len(decisions)}条设备决策")

        # 按用户拆分结果并写入数据库
        user_decision_map = {}
        for decision in decisions:
            new_device_id = decision.get("deviceId")  # JAR返回的是新ID
            original_device_id = new_id_original_id_map.get(new_device_id)  # 新ID→原ID
            # 从映射表获取序列号+数据库Device ID
            serial_db_tuple = original_id_serial_map.get(original_device_id)
            if not serial_db_tuple:
                log.warning(f"决策新ID={new_device_id}（原ID={original_device_id}）无对应设备信息，跳过落库")
                continue
            serial_num, db_device_id = serial_db_tuple  # 解包序列号+数据库ID
            user_id = serial_user_map.get(serial_num)  # 序列号→用户ID

            if not user_id:
                log.warning(f"决策新ID={new_device_id}（原ID={original_device_id}）无法关联用户，跳过落库")
                continue
            if user_id not in user_decision_map:
                user_decision_map[user_id] = []

            # 还原决策中的deviceId为原ID
            decision["deviceId"] = original_device_id
            # 临时存储数据库Device ID到decision，方便写入时使用
            decision["_db_device_id"] = db_device_id
            user_decision_map[user_id].append(decision)

        # 复用数据库连接，批量写入
        db = SessionLocal()
        try:
            for user_id, user_decisions in user_decision_map.items():
                user_full_result = {**full_result, "decisions": user_decisions}
                # 传入映射表，避免写入时再次查找
                write_strategy_to_db(db, cycle_time, user_full_result, user_id, original_id_serial_map)
            db.commit()
        except Exception as e:
            db.rollback()
            log.error(f"批量落库失败：{str(e)}")
        finally:
            db.close()

        # 更新内存状态
        with STORAGE_LOCK:
            DEVICE_STRATEGIES[cycle_time] = decisions
            CYCLE_STATUS[cycle_time] = "completed"

        return java_result

    except Exception as e:
        log.error(f"JAR调用/落库异常：{str(e)}", exc_info=True)
        with STORAGE_LOCK:
            CYCLE_STATUS[cycle_time] = "failed"
        return None


def write_strategy_to_db(db, cycle_time, full_result, current_user_id, original_id_serial_map):
    """
    严格按数据库表设计写入博弈结果（核心修改：使用数据库Device主键ID）
    匹配表：ystc_game_strategy / ystc_strategy_detail / ystc_control_command
    """
    try:
        # 解析周期时间
        cycle_start_time = datetime.fromisoformat(cycle_time).astimezone(AUS_TZ)
        cycle_end_time = cycle_start_time + timedelta(seconds=config.CYCLE_INTERVAL)
        time_slices = len(full_result["decisions"][0]["dc"]) if full_result.get("decisions") and full_result["decisions"] else 1
        time_slice_interval_sec = config.CYCLE_INTERVAL / time_slices  # 时间片间隔（秒）

        # 验证用户存在
        user = db.query(YstcUser).get(current_user_id)
        if not user:
            log.warning(f"用户ID{current_user_id}不存在，跳过落库")
            return False

        # 写入ystc_game_strategy表
        # 深拷贝避免修改原数据
        full_result_copy = json.loads(json.dumps(full_result))
        for decision in full_result_copy.get("decisions", []):
            original_device_id = decision.get("deviceId")
            serial_db_tuple = original_id_serial_map.get(original_device_id)
            if serial_db_tuple:
                _, db_device_id = serial_db_tuple
                decision["deviceId"] = db_device_id  # 替换为数据库Device主键ID
        strategy_json_str = json.dumps(full_result_copy, ensure_ascii=False)

        strategy_dict = json.loads(strategy_json_str)
        # 遍历decisions，删除每个decision中的_db_device_id字段
        for decision in strategy_dict.get("decisions", []):
            decision.pop("_db_device_id", None)
        # 重新生成无_db_device_id的JSON字符串
        strategy_json_str = json.dumps(strategy_dict, ensure_ascii=False)

        game_strategy = GameStrategy(
            user_id=current_user_id,
            strategy_name=f"周期{cycle_time[:19]}_用户{user.username}_博弈策略",
            strategy_type="博弈优化策略",
            algorithm_version="1.0",
            start_time=cycle_start_time,
            end_time=cycle_end_time,
            time_slices=time_slices,
            time_slice_interval=time_slice_interval_sec,
            strategy_params=json.dumps({
                "iteration": full_result.get("iteration", 0),
                "time_consumption": full_result.get("timeConsumption", 0.0),
                "total_benefit": full_result.get("benefit", 0.0),
                "total_cost": full_result.get("cost", 0.0),
                "revenue": full_result.get("revenue", 0.0)
            }, ensure_ascii=False),
            strategy_json=strategy_json_str,
            external_conditions="默认市场电价+基准电网负荷",
            is_active=True,
            status="已生成",
            create_by=user.username,
            create_time=datetime.now(AUS_TZ),
            update_by=user.username,
            update_time=datetime.now(AUS_TZ)
        )
        db.add(game_strategy)
        db.flush()
        strategy_id = game_strategy.id

        # 写入ystc_strategy_detail表
        for decision in full_result.get("decisions", []):
            # 直接从临时字段获取数据库Device ID
            db_device_id = decision.get("_db_device_id")
            if not db_device_id:
                original_device_id = decision.get("deviceId")
                serial_db_tuple = original_id_serial_map.get(original_device_id)
                if not serial_db_tuple:
                    log.warning(f"决策原ID={original_device_id}无对应设备信息，跳过详情写入")
                    continue
                _, db_device_id = serial_db_tuple

            # 验证设备归属当前用户
            device = db.query(Device).filter_by(id=db_device_id, user_id=current_user_id).first()
            if not device:
                log.warning(f"用户{current_user_id}无设备ID={db_device_id}，跳过详情写入")
                continue

            # 遍历时间片写入详情
            for time_slice_idx in range(time_slices):
                time_point = cycle_start_time + timedelta(seconds=time_slice_idx * time_slice_interval_sec)
                dc_value = decision["dc"][time_slice_idx]
                action_type = {
                    0: "idle",
                    1: "charge",
                    -1: "discharge"
                }.get(dc_value, "unknown")

                speed_value = decision["speed"][time_slice_idx]
                cost_value = decision["cost"][time_slice_idx] if len(decision.get("cost", [])) > time_slice_idx else 0.0
                total_benefit = decision.get("benefit", 0.0)

                strategy_detail = StrategyDetail(
                    strategy_id=strategy_id,
                    time_slice_index=time_slice_idx,
                    time_point=time_point,
                    action_type=action_type,
                    power_setpoint=speed_value,
                    expected_price=cost_value,
                    expected_benefit=total_benefit,
                    create_by=user.username,
                    create_time=datetime.now(AUS_TZ),
                    update_by=user.username,
                    update_time=datetime.now(AUS_TZ)
                )
                db.add(strategy_detail)

        # 写入ystc_control_command表
        for decision in full_result.get("decisions", []):
            # 直接从临时字段获取数据库Device ID
            db_device_id = decision.get("_db_device_id")
            if not db_device_id:
                original_device_id = decision.get("deviceId")
                serial_db_tuple = original_id_serial_map.get(original_device_id)
                if not serial_db_tuple:
                    continue
                _, db_device_id = serial_db_tuple

            # 验证设备归属当前用户
            device = db.query(Device).filter_by(id=db_device_id, user_id=current_user_id).first()
            if not device:
                continue

            # 解析命令类型
            dc_value = decision["dc"][0]
            command_type = {
                0: "idle_exec",
                1: "charge_exec",
                -1: "discharge_exec"
            }.get(dc_value, "unknown_exec")

            scheduled_at = cycle_start_time + timedelta(seconds=0 * time_slice_interval_sec)
            expire_at = scheduled_at + timedelta(seconds=time_slice_interval_sec)

            # 构建控制命令（核心：device_id使用数据库主键ID）
            control_command = ControlCommand(
                device_id=db_device_id,  # 最终写入数据库的设备ID（主键）
                strategy_id=strategy_id,
                command_type=command_type,
                command_params=json.dumps({
                    "dc": decision.get("dc", []),
                    "speed": decision.get("speed", []),
                    "cost": decision.get("cost", []),
                    "benefit": decision.get("benefit", 0.0),
                    "deviceId": db_device_id  # 数据库ID
                }, ensure_ascii=False),
                priority=1,
                issued_at=datetime.now(AUS_TZ),
                scheduled_at=scheduled_at,
                expire_at=expire_at,
                executed_at=None,
                status="pending",
                result=None,
                error_message=None,
                retry_count=0,
                max_retries=3,
                create_by=user.username,
                create_time=datetime.now(AUS_TZ),
                update_by=user.username,
                update_time=datetime.now(AUS_TZ)
            )
            db.add(control_command)

        # 最终提交所有变更
        db.commit()
        log.info(f"用户{current_user_id}（{user.username}）周期{cycle_time}博弈结果落库成功 | 策略ID：{strategy_id}")
        return True

    except Exception as e:
        db.rollback()
        log.error(f"用户{current_user_id}周期{cycle_time}落库失败：{str(e)}", exc_info=True)
        raise e