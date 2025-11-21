import os, json, logging
from datetime import datetime
from flask import Flask, request, jsonify
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# 基础配置
app = Flask(__name__)
# 日志配置
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
log = logging.getLogger("test")

# ===== 数据库配置=====
Base = declarative_base()

# 独立测试表
class TestUpload(Base):
    __tablename__ = "test_upload"  # 测试表名，测完直接删
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(50), nullable=False)  # 模拟设备ID
    test_data = Column(Float, nullable=False)  # 测试数据
    upload_time = Column(DateTime, default=datetime.now, nullable=False)  # 上传时间

# 数据库连接（本地测试时为本地MySQL，上云后改云端数据库）

# 格式：mysql+pymysql://用户名:密码@localhost:端口/数据库名?charset=utf8mb4
DATABASE_URI = "mysql+pymysql://root:root115@localhost:3306/ystc_energy?charset=utf8mb4"

# 数据库引擎
engine = create_engine(
    DATABASE_URI,
    pool_size=50,
    max_overflow=100,
    pool_pre_ping=True,
    echo=False  # 关闭SQL打印，提升速度
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 数据库初始化
def init_db():
    try:
        Base.metadata.create_all(bind=engine)  # 自动创建test_upload表
        log.info("测试表test_upload创建成功（已存在则跳过）")
        # 验证连接
        db = SessionLocal()
        db.query(TestUpload).first()
        db.close()
        log.info("数据库连接成功")
    except Exception as e:
        log.error(f"数据库初始化失败：{str(e)}")
        raise e

# 核心测试接口（创建一个用于压测）
@app.route("/api/test/upload", methods=["POST"])
def test_upload():
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"code": 400, "msg": "请求格式错误，需为JSON"}), 400

        if not all(key in data for key in ["device_id", "test_data"]):
            return jsonify({"code": 400, "msg": "缺少必填参数：device_id/test_data"}), 400

        db = SessionLocal()
        try:
            record = TestUpload(
                device_id=data["device_id"],
                test_data=round(float(data["test_data"]), 2)
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            db.close()
            return jsonify({
                "code": 200,
                "msg": "数据写入成功",
                "data_id": record.id
            }), 200
        except Exception as e:
            db.rollback()
            db.close()
            log.error(f"写入失败：{str(e)}")
            return jsonify({"code": 500, "msg": f"写入数据库失败：{str(e)}"}), 500
    except Exception as e:
        log.error(f"接口处理失败：{str(e)}")
        return jsonify({"code": 400, "msg": f"请求处理失败：{str(e)}"}), 400


# 辅助接口
@app.route("/api/test/drop_table", methods=["GET"])
def drop_test_table():
    """一键删除测试表（测完调用一次即可，谨慎使用！）"""
    try:
        db = SessionLocal()
        TestUpload.__table__.drop(bind=engine, checkfirst=True)  # checkfirst=True：表存在才删除
        db.close()
        log.info("测试表test_upload已删除")
        return jsonify({"code": 200, "msg": "测试表删除成功"}), 200
    except Exception as e:
        log.error(f"删表失败：{str(e)}")
        return jsonify({"code": 500, "msg": f"删表失败：{str(e)}"}), 500

# 健康检查接口
@app.route("/health", methods=["GET"])
def health_check():
    """简单健康检查，本地/云端都可调用"""
    try:
        db = SessionLocal()
        db.query(TestUpload).first()
        db.close()
        return jsonify({
            "code": 200,
            "status": "running",
            "db_status": "connected"
        }), 200
    except Exception as e:
        return jsonify({
            "code": 500,
            "status": "error",
            "db_status": f"disconnected: {str(e)}"
        }), 500

# ===== 启动入口=====
if __name__ == "__main__":
    # 初始化数据库（创建测试表）
    init_db()
    from waitress import serve
    log.info(f"用Waitress启动服务，端口：5002")
    serve(app, host='0.0.0.0', port=5002, threads=20)  # threads=20：20个工作线程（根据服务器CPU调整）