import logging
from flask import Blueprint, request, jsonify, g
from app.utils import (
    login_required, get_current_cycle, is_upload_window_open,
    DEVICE_DATA, STORAGE_LOCK, SessionLocal
)
from app.models import GameStrategy, StrategyDetail, ControlCommand

device_bp = Blueprint("device", __name__, url_prefix="/api/device")
log = logging.getLogger("pt.api.device")


# 数据上传接口
@device_bp.route("/upload", methods=["POST"])
@login_required
def upload_device_data():
    try:
        req_data = request.get_json()
        device_data = req_data.get("device_data")
        current_cycle = get_current_cycle()
        device_id_str = str(g.device.serial_number)

        if not device_data:
            return jsonify({
                "code": 400,
                "msg": "缺少device_data参数",
                "current_cycle": current_cycle
            }), 400

        if not is_upload_window_open(current_cycle):
            with STORAGE_LOCK:
                cycle_status = DEVICE_DATA.get(current_cycle, {}).get("status", "unknown")
            return jsonify({
                "code": 403,
                "msg": f"上传窗口已关闭（周期状态：{cycle_status}）",
                "current_cycle": current_cycle
            }), 403

        # 初始化当前周期的DEVICE_DATA字典
        with STORAGE_LOCK:
            if current_cycle not in DEVICE_DATA:
                DEVICE_DATA[current_cycle] = {}  # 先创建空字典
            DEVICE_DATA[current_cycle][device_id_str] = device_data

        log.info(f"数据上传成功：设备{device_id_str}，周期{current_cycle}")
        return jsonify({
            "code": 200,
            "msg": "上传成功",
            "cycle_time": current_cycle,
            "serial_number": device_id_str
        }), 200

    except Exception as e:
        log.error(f"数据上传失败：{str(e)}", exc_info=True)
        return jsonify({"code": 500, "msg": f"上传失败：{str(e)}"}), 500


# 策略查询接口
@device_bp.route("/get_strategy", methods=["GET"])
@login_required
def get_strategy():
    try:
        cycle_time = request.args.get("cycle_time")
        device = g.device

        if not cycle_time:
            return jsonify({"code": 400, "msg": "缺少cycle_time参数"}), 400

        db = SessionLocal()
        try:
            # GameStrategy按user_id关联
            game_strategy = db.query(GameStrategy).filter(
                GameStrategy.user_id == g.user.id,
                GameStrategy.strategy_name.like(f"%{cycle_time}%")  # 按周期时间模糊匹配
            ).first()

            if not game_strategy:
                return jsonify({"code": 404, "msg": "未找到该周期策略"}), 404

            details = db.query(StrategyDetail).filter(
                StrategyDetail.strategy_id == game_strategy.id
            ).order_by(StrategyDetail.time_slice_index).all()

            strategy_details = []
            for detail in details:
                strategy_details.append({
                    "time_slice_index": detail.time_slice_index,
                    "time_point": detail.time_point.isoformat(),
                    "action_type": detail.action_type,
                    "power_setpoint": detail.power_setpoint,
                    "expected_benefit": detail.expected_benefit
                })

            command = db.query(ControlCommand).filter(
                ControlCommand.strategy_id == game_strategy.id,
                ControlCommand.device_id == device.id
            ).first()

            return jsonify({
                "code": 200,
                "serial_number": device.serial_number,
                "cycle_time": cycle_time,
                "strategy": {
                    "strategy_id": game_strategy.id,
                    "start_time": game_strategy.start_time.isoformat(),
                    "end_time": game_strategy.end_time.isoformat(),
                    "expected_benefit": game_strategy.strategy_params.get("total_benefit"),
                    "details": strategy_details,
                    "command_params": command.command_params if command else None
                }
            }), 200

        except Exception as e:
            log.error(f"策略查询失败：{str(e)}")
            return jsonify({"code": 500, "msg": f"查询失败：{str(e)}"}), 500
        finally:
            db.close()

    except Exception as e:
        log.error(f"策略查询接口异常：{str(e)}", exc_info=True)
        return jsonify({"code": 500, "msg": f"查询失败：{str(e)}"}), 500


# 当前周期接口
@device_bp.route("/current_cycle", methods=["GET"])
@login_required
def get_current_cycle_api():
    try:
        current_cycle = get_current_cycle()
        return jsonify({
            "code": 200,
            "msg": "获取成功",
            "current_cycle": current_cycle
        }), 200
    except Exception as e:
        log.error(f"获取当前周期失败：{str(e)}", exc_info=True)
        return jsonify({
            "code": 500,
            "msg": "获取当前周期失败",
            "error": str(e)
        }), 500