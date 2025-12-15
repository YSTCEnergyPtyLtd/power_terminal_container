import logging
from functools import wraps
from datetime import datetime
import pytz
import jwt
from jwt.exceptions import InvalidTokenError
from flask import request, jsonify, g, redirect, url_for
from app.utils.db import SessionLocal
from app.models import YstcUser, Device, UserAuthToken
from ..config import config

log = logging.getLogger("pt.auth")
AUS_TZ = pytz.timezone(config.TZ)


def login_required(f):
    """API接口鉴权装饰器：验证Token有效性"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 获取Token
        token = request.headers.get("Authorization")
        if not token or not token.startswith("Bearer "):
            return jsonify({"code": 401, "msg": "未提供有效认证Token"}), 401

        token = token[7:]
        db = SessionLocal()

        try:
            # 解码Token（关闭过期校验，因为Token永久有效）
            payload = jwt.decode(
                token,
                config.JWT_SECRET_KEY,
                algorithms=["HS256"],
                options={"verify_exp": False}
            )

            user_id = payload.get("user_id")
            # 生成Token哈希
            token_hash = jwt.encode(payload, config.JWT_SECRET_KEY, algorithm="HS256")
            if isinstance(token_hash, bytes):
                token_hash = token_hash.decode("utf-8")

            # 验证Token是否有效（未失效、用户/设备存在）
            auth_token = db.query(UserAuthToken).filter(
                UserAuthToken.user_id == user_id,
                UserAuthToken.token_hash == token_hash,
                UserAuthToken.is_valid == True
            ).first()

            if not auth_token:
                return jsonify({"code": 401, "msg": "Token无效或已注销"}), 401

            # 验证用户和设备存在
            user = db.query(YstcUser).filter(YstcUser.id == user_id).first()
            device = db.query(Device).filter(Device.user_id == user_id).first()

            if not user or not device:
                auth_token.is_valid = False
                db.commit()
                return jsonify({"code": 401, "msg": "账号/设备已失效"}), 401

            # 更新设备在线状态
            device.status = "online"
            device.last_online = datetime.now(AUS_TZ)
            db.commit()

            # 存入g对象
            g.user = user
            g.device = device
            return f(*args, **kwargs)

        except InvalidTokenError as e:
            return jsonify({"code": 401, "msg": f"Token解析失败：{str(e)}"}), 401
        except Exception as e:
            log.error(f"鉴权异常：{str(e)}")
            return jsonify({"code": 500, "msg": f"鉴权失败：{str(e)}"}), 500
        finally:
            db.close()

    return decorated_function


def page_login_required(f):
    """页面鉴权装饰器：验证Token并控制页面访问"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 从Header或Cookie获取Token
        token = request.headers.get("Authorization")
        if not token:
            token = request.cookies.get("access_token")
            if token:
                token = f"Bearer {token}"

        if not token or not token.startswith("Bearer "):
            return redirect(url_for("auth.login_page"))

        token = token[7:]
        db = SessionLocal()

        try:
            # 解码Token
            payload = jwt.decode(
                token,
                config.JWT_SECRET_KEY,
                algorithms=["HS256"],
                options={"verify_exp": False}
            )

            user_id = payload.get("user_id")
            token_hash = jwt.encode(payload, config.JWT_SECRET_KEY, algorithm="HS256")
            if isinstance(token_hash, bytes):
                token_hash = token_hash.decode("utf-8")

            # 验证Token有效性
            auth_token = db.query(UserAuthToken).filter(
                UserAuthToken.user_id == user_id,
                UserAuthToken.token_hash == token_hash,
                UserAuthToken.is_valid == True
            ).first()

            user = db.query(YstcUser).filter(YstcUser.id == user_id).first()
            device = db.query(Device).filter(Device.user_id == user_id).first()

            if not auth_token or not user or not device:
                return redirect(url_for("auth.login_page"))

            # 存入g对象
            g.user = user
            g.device = device
            return f(*args, **kwargs)

        except Exception as e:
            log.error(f"页面鉴权异常：{str(e)}")
            return redirect(url_for("auth.login_page"))
        finally:
            db.close()

    return decorated_function