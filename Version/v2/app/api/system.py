import logging
from flask import Blueprint, request, jsonify, render_template
from app.utils import SessionLocal
from app.models import YstcUser, Device, UserAuthToken, GameStrategy, StrategyDetail, ControlCommand

# 创建蓝图
system_bp = Blueprint("system", __name__, url_prefix="")
log = logging.getLogger("pt.api.system")


@system_bp.route("/reset", methods=["GET", "POST"])
def reset_data():
    """重置所有数据接口"""
    if request.method == "GET":
        return render_template("reset.html")

    try:
        db = SessionLocal()
        try:
            # 级联删除所有数据（按外键顺序）
            db.query(ControlCommand).delete()
            db.query(StrategyDetail).delete()
            db.query(GameStrategy).delete()
            db.query(UserAuthToken).delete()
            db.query(Device).delete()
            db.query(YstcUser).delete()

            db.commit()
            log.info("所有数据已重置")
            return jsonify({"code": 200, "msg": "重置成功"}), 200

        except Exception as e:
            db.rollback()
            log.error(f"重置失败：{str(e)}")
            return jsonify({"code": 500, "msg": f"重置失败：{str(e)}"}), 500
        finally:
            db.close()

    except Exception as e:
        log.error(f"重置接口异常：{str(e)}")
        return jsonify({"code": 500, "msg": f"接口异常：{str(e)}"}), 500