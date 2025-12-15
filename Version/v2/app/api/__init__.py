from flask import Flask
from app.api.auth import auth_bp
from app.api.device import device_bp
from app.api.system import system_bp

def register_blueprints(app: Flask):
    """注册所有蓝图"""
    app.register_blueprint(auth_bp)
    app.register_blueprint(device_bp)
    app.register_blueprint(system_bp)

__all__ = ["register_blueprints"]