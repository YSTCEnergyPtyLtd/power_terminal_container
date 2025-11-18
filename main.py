import asyncio, os, json, logging, threading,uuid
from datetime import datetime, timedelta
import pytz
from flask import Flask, request, render_template, jsonify
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Float, JSON, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from config import config

# ===== 基本参数 =====
# 修改为从config中读取
AUS_TZ = pytz.timezone(config.TZ)
DATA_DIR = config.DATA_DIR
LOG_DIR = config.LOG_DIR
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# ===== 日志 =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "power_terminal.log"), encoding="utf-8"),
        logging.StreamHandler()
    ],
)
log = logging.getLogger("pt")

# ===== 运行状态（给 /health 用）=====
STATE = {
    "booted": False,
    "web_started": False,
    "loop_started": False,
    "user_file_seen": False,
    "db_status": "disconnected",  # 新添加一个数据库连接状态
    "last_cycle_start": None,
    "last_cycle_end": None,
    "next_quarter_wait_sec": None,
    "last_error": None,
}

# ===== 数据库核心配置（ORM模型+连接）=====
# 模型基类（所有数据库表模型继承此类）
Base = declarative_base()
class YstcUser(Base):
    __tablename__ = "ystc_user"  # 数据库表名
    id = Column(Integer, primary_key=True, autoincrement=True)  # 主键（自增，数据库自动生成）
    username = Column(String(50), unique=True, nullable=False)  # 用户名（唯一标识，用户输入）
    password_hash = Column(String(128), nullable=False)  # 密码哈希（需加密存储）
    name = Column(String(50), nullable=False)  # 姓名（用户输入）
    phone = Column(String(20), nullable=False)  # 手机号（用户输入）
    email = Column(String(100), nullable=False)  # 邮箱（用户输入）
    address = Column(String(200), nullable=False)  # 地址（用户输入）
    powerline_info = Column(String(200), nullable=True)  # 可选字段
    is_active = Column(Boolean, default=True, nullable=True)  # 默认激活
    last_login = Column(DateTime, nullable=True)  # 最后登录时间
    create_by = Column(String(50), default="system", nullable=True)  # 创建人
    create_time = Column(DateTime, default=lambda: datetime.now(AUS_TZ), nullable=True)  # 创建时间
    update_by = Column(String(50), nullable=True)  # 更新人
    update_time = Column(DateTime, nullable=True)  # 更新时间

# 数据库连接引擎（从config读取连接信息）
engine = create_engine(
    config.SQLALCHEMY_DATABASE_URI,
    pool_size=20,  # 连接池大小（支持多并发）
    max_overflow=30,  # 最大溢出连接数
    pool_pre_ping=True  # 自动检测无效连接，避免连接失效
)
# 数据库会话工厂（每次操作数据库都通过会话）
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 数据库表初始化（首次运行自动创建表，已存在则无操作）
def init_db():
    try:
        Base.metadata.create_all(bind=engine)  # 创建所有模型对应的表
        log.info("数据库表初始化完成（若已存在则跳过）")
        # 测试数据库连接
        db = SessionLocal()
        db.query(YstcUser).first()  # 执行简单查询
        db.close()
        STATE["db_status"] = "connected"
        log.info("数据库连接成功")
    except Exception as e:
        STATE["db_status"] = f"disconnected: {str(e)}"
        log.error(f"数据库初始化/连接失败：{str(e)}")


# ===== 核心任务（模拟）=====
async def read_meter_data():
    log.info("读取电表数据（模拟）")
    await asyncio.sleep(1)
    return {"power_kw": 10.5}

async def forecast_power(meter_data):
    log.info("预测下一时段用电量（模拟）")
    await asyncio.sleep(1)
    return meter_data["power_kw"] * 1.05

async def get_cloud_strategy(predicted_power):
    log.info("调用云端博弈（模拟）")
    await asyncio.sleep(1)


    return {"action": "DISCHARGE", "power_kw": -3} if predicted_power > 11 else {"action": "CHARGE", "power_kw": 3}

async def control_battery(strategy):
    log.info(f"执行策略：{strategy['action']}，功率 {strategy['power_kw']} kW")
    await asyncio.sleep(1)
    log.info("执行完成")



# ===== 整刻对时 =====
async def align_to_next_quarter():
    now = datetime.now(AUS_TZ)
    minute = (now.minute // 15 + 1) * 15
    hour = now.hour
    if minute >= 60:
        minute = 0
        hour = (hour + 1) % 24
    next_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_time <= now:
        next_time += timedelta(minutes=15)
    wait_s = (next_time - now).total_seconds()
    STATE["next_quarter_wait_sec"] = wait_s
    log.info(f"距离下一个整刻还有 {wait_s:.1f} 秒...")
    await asyncio.sleep(wait_s)

# ===== 单个周期 =====
async def run_cycle():
    STATE["last_cycle_start"] = datetime.now(AUS_TZ).isoformat()
    log.info(f"=== 周期开始：{datetime.now(AUS_TZ).strftime('%Y-%m-%d %H:%M:%S')} ===")
    meter = await read_meter_data()
    pred  = await forecast_power(meter)
    strat = await get_cloud_strategy(pred)
    await control_battery(strat)
    log.info(f"=== 周期结束：{datetime.now(AUS_TZ).strftime('%H:%M:%S')} ===\n")
    STATE["last_cycle_end"] = datetime.now(AUS_TZ).isoformat()

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        data = {
            "username": request.form.get("username", "").strip(),
            "name": request.form.get("name", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "email": request.form.get("email", "").strip(),
            "addr": request.form.get("addr", "").strip(),
        }
        if not all(data.values()):
            return render_template("form.html")

        db = SessionLocal()
        try:
            # 校验用户名唯一性
            existing_user = db.query(YstcUser).filter(YstcUser.username == data["username"]).first()
            if existing_user:
                return "用户名已存在，请更换后重试！"

            # 构造用户数据（密码哈希需后续添加，此处示例省略）
            user_data = {
                "username": data["username"],
                "name": data["name"],
                "phone": data["phone"],
                "email": data["email"],
                "address": data["addr"],
                "password_hash": "默认哈希（需替换为真实加密逻辑）",  # 示例：实际需用bcrypt等加密
            }
            new_user = YstcUser(**user_data)
            db.add(new_user)
            db.commit()
            log.info(f"注册完成，用户ID（id）：{new_user.id}，用户名：{data['username']}")
            return "注册成功！系统将进入15分钟整刻循环。可关闭此页面。"
        except Exception as e:
            db.rollback()
            log.error(f"注册失败：{str(e)}")
            return f"注册失败：{str(e)}"
        finally:
            db.close()

    db = SessionLocal()
    has_user = db.query(YstcUser).first() is not None
    db.close()
    if has_user:
        return render_template("registered.html")
    return render_template("form.html")

# 修改
# @app.route("/reset", methods=["POST"])
# def reset_registration():
#     db = SessionLocal()
#     try:
#         # 清空用户表所有记录
#         db.query(YstcUser).delete()
#         db.commit()
#         log.info("用户注册信息已重置（数据库用户表清空）")
#         return render_template("reset.html")
#     except Exception as e:
#         db.rollback()
#         log.error(f"重置失败：{str(e)}")
#         return f"重置失败：{str(e)}"
#     finally:
#         db.close()


@app.route("/health")
def health():
    # 实时更新数据库连接状态
    try:
        db = SessionLocal()
        db.query(YstcUser).first()
        db.close()
        STATE["db_status"] = "connected"
    except Exception as e:
        STATE["db_status"] = f"disconnected: {str(e)}"

    # 实时检测是否已注册（数据库查询）
    db = SessionLocal()
    STATE["user_file_seen"] = db.query(YstcUser).first() is not None
    db.close()

    return jsonify(STATE)

# ===== 后台异步循环 =====
async def service_loop():
    try:
        STATE["loop_started"] = True
        log.info("系统（调控循环）启动")

        # 从数据库查询
        db = SessionLocal()
        while not db.query(YstcUser).first():
            db.close()
            STATE["user_file_seen"] = False
            await asyncio.sleep(1)
            db = SessionLocal()
        db.close()
        STATE["user_file_seen"] = True
        log.info("检测到已注册用户，启动15分钟整刻循环")

        # 进入15分钟循环
        while True:
            await align_to_next_quarter()
            await run_cycle()
    except Exception as e:
        STATE["last_error"] = repr(e)
        log.exception("后台循环异常")

# ===== 启动顺序：主线程跑 async，子线程跑 Flask（最稳）=====
def start_web_server():
    STATE["web_started"] = True
    log.info("启动 Web 注册服务 (Flask) on :8080")
    app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False, threaded=True)

def main():
    init_db()
    STATE["booted"] = True
    log.info("BOOT: 进程启动，准备启动 Web 与后台循环")
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()
    asyncio.run(service_loop())

if __name__ == "__main__":
    main()
