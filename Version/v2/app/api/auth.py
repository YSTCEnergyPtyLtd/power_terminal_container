import logging
from datetime import datetime, timedelta  # 新增：导入timedelta
import pytz
import jwt
from jwt.exceptions import InvalidTokenError
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, g, make_response
from app.utils import SessionLocal, login_required, page_login_required
from app.models import YstcUser, Device, UserAuthToken
from sqlalchemy.exc import OperationalError
from ..config import config
import time

auth_bp = Blueprint("auth", __name__, url_prefix="")
log = logging.getLogger("pt.api.auth")
AUS_TZ = pytz.timezone(config.TZ)


# 根路由→跳登录页
@auth_bp.route("/")
def index():
    return redirect(url_for("auth.login_page"))


# 登录页
@auth_bp.route("/login")
def login_page():
    return render_template("login.html")


# 注册页
@auth_bp.route("/register")
def register_page():
    return render_template("register.html")


# 仪表盘页
@auth_bp.route("/dashboard")
@page_login_required
def dashboard_page():
    return render_template(
        "dashboard.html",
        username=g.user.username,
        serial_number=g.device.serial_number
    )


# 注册接口
@auth_bp.route("/api/device/register", methods=["POST"])
def device_register():
    try:
        data = request.get_json()
        required_fields = ["username", "password", "serial_number", "device_name", "device_type"]

        if not all(field in data for field in required_fields):
            return jsonify({
                "code": 400,
                "msg": "缺少必填字段：username/password/serial_number/device_name/device_type"
            }), 400

        db = SessionLocal()
        try:
            # 校验唯一性
            if db.query(YstcUser).filter(YstcUser.username == data["username"]).first():
                return jsonify({"code": 400, "msg": "账号已存在"}), 400

            if db.query(Device).filter(Device.serial_number == data["serial_number"]).first():
                return jsonify({"code": 400, "msg": "设备序列号已注册"}), 400

            # 创建用户
            user = YstcUser(
                username=data["username"],
                password_hash=data["password"],  # 生产环境需用bcrypt加密
                name=data["device_name"],
                phone=data.get("phone"),
                email=data.get("email"),
                address=data.get("address"),
                create_by=data["username"],
                create_time=datetime.now(AUS_TZ),
                is_active=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            # 创建设备
            device = Device(
                serial_number=data["serial_number"],
                type=data["device_type"],
                model=data.get("model"),
                firmware_version=data.get("firmware_version"),
                user_id=user.id,
                location=data.get("address"),
                create_by=data["username"],
                create_time=datetime.now(AUS_TZ),
                is_active=True
            )
            db.add(device)
            db.commit()

            log.info(f"注册成功：账号={data['username']}，设备SN={data['serial_number']}，用户ID={user.id}")
            return jsonify({
                "code": 200,
                "msg": "注册成功，请登录",
                "user_id": user.id,
                "device_id": device.id,
                "serial_number": device.serial_number
            }), 200

        except Exception as e:
            db.rollback()
            log.error(f"注册失败：{str(e)}", exc_info=True)
            return jsonify({"code": 500, "msg": f"注册失败：{str(e)}"}), 500
        finally:
            db.close()

    except Exception as e:
        log.error(f"注册接口异常：{str(e)}", exc_info=True)
        return jsonify({"code": 500, "msg": f"接口异常：{str(e)}"}), 500


def retry_on_deadlock(max_retries=3, delay=1):
    def decorator(func):
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except OperationalError as e:
                    # 检测死锁错误码 1213
                    if e.orig.args[0] == 1213:
                        retries += 1
                        log.warning(f"捕获死锁异常，第{retries}次重试（延迟{delay * retries}秒）")
                        time.sleep(delay * retries)
                        continue
                    raise
                except Exception as e:
                    raise
            raise Exception(f"超过{max_retries}次重试仍死锁，操作失败")

        return wrapper

    return decorator


# 登录接口
@auth_bp.route("/api/device/login", methods=["POST"])
@retry_on_deadlock(max_retries=3, delay=1)  # 死锁重试装饰器
def device_login():
    try:
        data = request.get_json()
        if not data.get("username") or not data.get("password"):
            return jsonify({"code": 400, "msg": "缺少账号/密码"}), 400

        db = SessionLocal()
        try:
            # 校验账号密码
            user = db.query(YstcUser).filter(YstcUser.username == data["username"]).first()
            if not user:
                log.warning(f"登录失败：账号{data['username']}不存在")
                return jsonify({"code": 401, "msg": "账号或密码错误"}), 401
            if user.password_hash != data["password"]:
                log.warning(f"登录失败：账号{data['username']}密码错误")
                return jsonify({"code": 401, "msg": "账号或密码错误"}), 401
            log.info(f"登录校验通过：账号{data['username']}，用户ID={user.id}")

            # 生成Token
            payload = {"user_id": user.id}
            access_token = jwt.encode(
                payload,
                config.JWT_SECRET_KEY.encode("utf-8") if isinstance(config.JWT_SECRET_KEY,
                                                                    str) else config.JWT_SECRET_KEY,
                algorithm="HS256"
            )
            refresh_token = jwt.encode(
                {"user_id": user.id, "refresh": True},
                config.JWT_SECRET_KEY.encode("utf-8") if isinstance(config.JWT_SECRET_KEY,
                                                                    str) else config.JWT_SECRET_KEY,
                algorithm="HS256"
            )

            # 转为字符串
            access_token = access_token.decode("utf-8") if isinstance(access_token, bytes) else access_token
            refresh_token = refresh_token.decode("utf-8") if isinstance(refresh_token, bytes) else refresh_token
            token_hash = access_token
            refresh_token_hash = refresh_token

            # 减少锁竞争
            # 只锁定当前用户的有效Token
            # 批量更新，减少数据库交互
            update_count = db.query(UserAuthToken).filter(
                UserAuthToken.user_id == user.id,
                UserAuthToken.is_valid == True
            ).update({
                "is_valid": False,
                "update_by": user.username,
                "update_time": datetime.now(AUS_TZ)
            }, synchronize_session=False)

            log.info(f"失效旧Token：用户ID={user.id}，失效数量={update_count}")

            # 创建新Token
            auth_token = UserAuthToken(
                user_id=user.id,
                token_hash=token_hash,
                refresh_token_hash=refresh_token_hash,
                expires_at=datetime.now(AUS_TZ) + timedelta(days=365 * 100),
                refresh_expires_at=datetime.now(AUS_TZ) + timedelta(days=365 * 100),
                client_info=f"IP:{request.remote_addr};UA:{request.user_agent.string}",
                is_valid=True,
                create_by=user.username,
                create_time=datetime.now(AUS_TZ),
                update_by=user.username,
                update_time=datetime.now(AUS_TZ)
            )
            db.add(auth_token)

            # 更新最后登录时间
            user.last_login = datetime.now(AUS_TZ)
            user.update_by = user.username
            user.update_time = datetime.now(AUS_TZ)

            # 快速提交事务，减少锁持有时间
            db.commit()

            log.info(f"登录成功：账号={data['username']}，生成Token哈希前10位={token_hash[:10]}")

            # 返回结果
            response = make_response(jsonify({
                "code": 200,
                "msg": "登录成功",
                "access_token": access_token,
                "refresh_token": refresh_token,
                "redirect": "/dashboard"
            }))
            response.set_cookie(
                "access_token",
                access_token,
                httponly=True,
                samesite="Lax",
                max_age=365 * 100 * 24 * 3600
            )

            return response

        except Exception as e:
            db.rollback()
            log.error(f"登录失败：{str(e)}", exc_info=True)
            if "foreign key" in str(e).lower():
                return jsonify({"code": 500, "msg": f"登录失败：用户ID={user.id}关联异常，请检查用户是否存在"}), 500
            return jsonify({"code": 500, "msg": f"登录失败：{str(e)}"}), 500
        finally:
            db.close()

    except Exception as e:
        log.error(f"登录接口异常：{str(e)}", exc_info=True)
        return jsonify({"code": 500, "msg": f"接口异常：{str(e)}"}), 500

# Token 校验接口
@auth_bp.route("/api/device/verify_token", methods=["POST"])
def verify_token():
    """校验Token是否有效（无需登录装饰器）"""
    try:
        # 获取前端传的Token
        data = request.get_json()
        token = data.get("access_token")

        if not token:
            return jsonify({"code": 401, "msg": "Token为空"}), 401

        # 解码并验证Token
        db = SessionLocal()
        try:
            # 解码Token（关闭过期校验）
            payload = jwt.decode(
                token,
                config.JWT_SECRET_KEY.encode("utf-8") if isinstance(config.JWT_SECRET_KEY, str) else config.JWT_SECRET_KEY,
                algorithms=["HS256"],
                options={"verify_exp": False}
            )
            user_id = payload.get("user_id")
            if not user_id:
                return jsonify({"code": 401, "msg": "Token中无用户ID"}), 401

            # 简化token_hash生成
            token_hash = token

            # 检查Token是否在数据库中且有效
            auth_token = db.query(UserAuthToken).filter(
                UserAuthToken.user_id == user_id,
                UserAuthToken.token_hash == token_hash,
                UserAuthToken.is_valid == True
            ).first()

            if not auth_token:
                log.warning(f"Token失效：用户ID={user_id}，Token前10位={token_hash[:10]}")
                return jsonify({"code": 401, "msg": "Token已失效"}), 401

            # 检查用户和设备是否存在
            user = db.query(YstcUser).filter(YstcUser.id == user_id).first()
            device = db.query(Device).filter(Device.user_id == user_id).first()

            if not user or not device:
                return jsonify({"code": 401, "msg": "账号/设备不存在"}), 401

            # Token有效，返回用户信息
            return jsonify({
                "code": 200,
                "msg": "Token有效",
                "data": {
                    "username": user.username,
                    "serial_number": device.serial_number
                }
            }), 200

        except InvalidTokenError as e:
            log.error(f"Token格式错误：{str(e)}")
            return jsonify({"code": 401, "msg": "Token格式错误"}), 401
        finally:
            db.close()

    except Exception as e:
        log.error(f"Token校验异常：{str(e)}", exc_info=True)
        return jsonify({"code": 500, "msg": "服务器异常"}), 500


# 退出登录接口
@auth_bp.route("/api/device/logout", methods=["POST"])
@login_required
def device_logout():
    try:
        token = request.headers.get("Authorization").split(" ")[1] if request.headers.get("Authorization") else ""
        if not token:
            return jsonify({"code": 400, "msg": "Token为空"}), 400
        user_id = g.user.id

        db = SessionLocal()
        try:
            # 解码Token
            payload = jwt.decode(
                token,
                config.JWT_SECRET_KEY.encode("utf-8") if isinstance(config.JWT_SECRET_KEY, str) else config.JWT_SECRET_KEY,
                algorithms=["HS256"],
                options={"verify_exp": False}
            )

            # 简化token_hash生成
            token_hash = token

            # 失效Token
            update_count = db.query(UserAuthToken).filter(
                UserAuthToken.user_id == user_id,
                UserAuthToken.token_hash == token_hash,
                UserAuthToken.is_valid == True
            ).update({
                "is_valid": False,
                "update_by": g.user.username,
                "update_time": datetime.now(AUS_TZ)
            })

            # 更新设备状态为离线
            g.device.status = "offline"
            g.device.update_by = g.user.username
            g.device.update_time = datetime.now(AUS_TZ)
            db.commit()

            # 清除Cookie
            response = make_response(jsonify({
                "code": 200 if update_count > 0 else 400,
                "msg": "退出成功" if update_count > 0 else "未找到有效登录状态",
                "redirect": "/login"
            }))
            response.set_cookie("access_token", "", expires=0)

            if update_count > 0:
                log.info(f"退出成功：账号={g.user.username}")
            else:
                log.warning(f"退出失败：账号={g.user.username}，无有效Token")

            return response

        except Exception as e:
            db.rollback()
            log.error(f"退出失败：{str(e)}", exc_info=True)
            return jsonify({"code": 500, "msg": f"退出失败：{str(e)}"}), 500
        finally:
            db.close()

    except Exception as e:
        log.error(f"退出接口异常：{str(e)}", exc_info=True)
        return jsonify({"code": 500, "msg": f"接口异常：{str(e)}"}), 500