# 该代码是基于内存的存储，让设备传输进行一个非持久化存储
# 然后到时间就call博弈模型
# 设备通过接口自行拉取结果。

import asyncio, os, json, logging, threading, uuid, re, subprocess, time
from datetime import datetime, timedelta, timezone
import pytz
from flask import Flask, request, render_template, jsonify
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Float, JSON, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker


# 配置
class Config:
    TZ = 'Australia/Sydney'
    DATA_DIR = './data'
    LOG_DIR = './logs'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///./user.db' # 测试用
    CYCLE_INTERVAL = 120  # 周期时长：2分钟 根据实际进行修改
    UPLOAD_WINDOW = 20  # 上传窗口：前20秒 根据需求修改
    TIME_SLOTS = 3  # 与JAR中的timeSlots保持一致


config = Config()

# 基本参数
AUS_TZ = pytz.timezone(config.TZ)
CYCLE_INTERVAL = config.CYCLE_INTERVAL
UPLOAD_WINDOW = config.UPLOAD_WINDOW
TIME_SLOTS = config.TIME_SLOTS
DATA_DIR = config.DATA_DIR
LOG_DIR = config.LOG_DIR
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# 日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "power_terminal.log"), encoding="utf-8"),
        logging.StreamHandler()
    ],
)
log = logging.getLogger("pt")

# 运行状态
STATE = {
    "booted": False,
    "web_started": False,
    "loop_started": False,
    "user_file_seen": False,
    "db_status": "disconnected",
    "last_cycle_start": None,
    "last_cycle_end": None,
    "last_error": None,
    "current_cycle": None,
    "current_cycle_status": "idle",
    "cycle_start_time": None,
}

# 设备数据存储
DEVICE_DATA = {}  # {周期时间: {设备ID: 完整设备数据（匹配JAR输入）}}
DEVICE_STRATEGIES = {}  # {周期时间: {设备ID: 策略结果}}
GAME_RESULTS = {}  # {周期时间: JAR完整输出结果}
CYCLE_STATUS = {}  # {周期时间: 状态（uploading/processing/completed）}
STORAGE_LOCK = threading.Lock()

# 数据库配置
Base = declarative_base()


class YstcUser(Base):
    __tablename__ = "ystc_user"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    name = Column(String(50), nullable=False)
    phone = Column(String(20), nullable=False)
    email = Column(String(100), nullable=False)
    address = Column(String(200), nullable=False)
    powerline_info = Column(String(200), nullable=True)
    is_active = Column(Boolean, default=True, nullable=True)
    last_login = Column(DateTime, nullable=True)
    create_by = Column(String(50), default="system", nullable=True)
    create_time = Column(DateTime, default=lambda: datetime.now(AUS_TZ), nullable=True)
    update_by = Column(String(50), nullable=True)
    update_time = Column(DateTime, nullable=True)


engine = create_engine(
    config.SQLALCHEMY_DATABASE_URI,
    pool_size=20,
    max_overflow=30,
    pool_pre_ping=True
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        log.info("数据库表初始化完成")
        db = SessionLocal()
        db.query(YstcUser).first()
        db.close()
        STATE["db_status"] = "connected"
        log.info("数据库连接成功")
    except Exception as e:
        STATE["db_status"] = f"disconnected: {str(e)}"
        log.error(f"数据库初始化失败：{str(e)}")


# 周期工具函数
def get_current_cycle():
    """生成当前周期标识（2分钟一个周期，基于系统启动时间）"""
    if not hasattr(get_current_cycle, "start_time"):
        get_current_cycle.start_time = time.time()
    elapsed = time.time() - get_current_cycle.start_time
    cycle_num = int(elapsed // CYCLE_INTERVAL)
    cycle_start_ts = get_current_cycle.start_time + cycle_num * CYCLE_INTERVAL
    cycle_id = datetime.fromtimestamp(cycle_start_ts, tz=AUS_TZ).isoformat()

    # 初始化周期状态
    with STORAGE_LOCK:
        if cycle_id not in CYCLE_STATUS:
            CYCLE_STATUS[cycle_id] = "uploading"
            DEVICE_DATA[cycle_id] = {}

    STATE["current_cycle"] = cycle_id
    STATE["current_cycle_status"] = CYCLE_STATUS[cycle_id]
    STATE["cycle_start_time"] = cycle_start_ts
    return cycle_id


def is_upload_window_open(cycle_id):
    """检查当前周期的上传窗口是否打开"""
    with STORAGE_LOCK:
        if cycle_id not in CYCLE_STATUS:
            return False
        if CYCLE_STATUS[cycle_id] != "uploading":
            return False

    cycle_start_ts = datetime.fromisoformat(cycle_id).timestamp()
    current_ts = time.time()
    return (current_ts - cycle_start_ts) < UPLOAD_WINDOW


def clean_expired_data():
    """清理超过1小时的过期数据"""
    cutoff_ts = time.time() - 3600
    with STORAGE_LOCK:
        expired_cycles = []
        for cycle in CYCLE_STATUS:
            cycle_ts = datetime.fromisoformat(cycle).timestamp()
            if cycle_ts < cutoff_ts:
                expired_cycles.append(cycle)

        for cycle in expired_cycles:
            DEVICE_DATA.pop(cycle, None)
            DEVICE_STRATEGIES.pop(cycle, None)
            GAME_RESULTS.pop(cycle, None)
            CYCLE_STATUS.pop(cycle, None)

    if expired_cycles:
        log.info(f"清理过期数据：{len(expired_cycles)}个周期")


# 调用JAR模型
async def call_jar_model(cycle_time):
    """调用JAR模型，严格处理设备数据格式"""
    jar_path = "game-model-1.0.jar"
    if not os.path.exists(jar_path):
        log.error(f"JAR文件不存在：{jar_path}")
        return None

    # 读取当前周期的设备数据
    with STORAGE_LOCK:
        current_devices = DEVICE_DATA.get(cycle_time, {})
        raw_devices = list(current_devices.values())  # 原始设备列表

    if not raw_devices:
        log.warning(f"周期{cycle_time}无设备数据，跳过JAR调用")
        with STORAGE_LOCK:
            CYCLE_STATUS[cycle_time] = "completed"
        return None

    # 处理设备数据
    processed_devices = []
    for device in raw_devices:
        if not isinstance(device, dict):
            log.error(f"无效设备数据：非字典格式")
            continue

        # 处理produce字段：缺失则填充[0]*TIME_SLOTS，存在则验证长度
        if "produce" not in device:
            device["produce"] = [0] * TIME_SLOTS
        else:
            if not isinstance(device["produce"], list) or len(device["produce"]) != TIME_SLOTS:
                log.error(f"设备[{device.get('id')}]produce字段错误，需为长度{TIME_SLOTS}的数组")
                device["produce"] = [0] * TIME_SLOTS

        # 确保id字段存在
        if "id" not in device:
            device["id"] = len(processed_devices)  # 自动分配id

        processed_devices.append(device)

    if not processed_devices:
        log.error(f"周期{cycle_time}无有效设备数据")
        with STORAGE_LOCK:
            CYCLE_STATUS[cycle_time] = "completed"
        return None

    # 构造JAR输入
    jar_input_json = json.dumps(processed_devices, ensure_ascii=False)
    log.info(f"JAR输入数据（处理后）：{jar_input_json[:300]}...")

    try:
        # 异步执行JAR
        result = await asyncio.to_thread(
            subprocess.run,
            ["java", "-jar", jar_path, jar_input_json],
            capture_output=True,
            text=True,
            timeout=30
        )

        # 处理JAR输出
        if result.returncode == 0:
            # 提取JSON结果
            json_match = re.search(r'\{[\s\S]*\}', result.stdout)
            if json_match:
                java_full_result = json.loads(json_match.group())

                # 提取userNum
                user_num_match = re.search(r'userNum:\s*(\d+)', result.stdout)
                user_num = int(user_num_match.group(1)) if user_num_match else len(processed_devices)

                # 构建设备策略映射
                strategy_map = {}
                if "decisions" in java_full_result and isinstance(java_full_result["decisions"], list):
                    for decision in java_full_result["decisions"]:
                        device_id = str(decision.get("deviceId", decision.get("id")))
                        strategy_map[device_id] = decision

                # 存储结果
                with STORAGE_LOCK:
                    GAME_RESULTS[cycle_time] = {
                        "userNum": user_num,
                        "full_result": java_full_result,
                        "raw_stdout": result.stdout
                    }
                    DEVICE_STRATEGIES[cycle_time] = strategy_map
                    CYCLE_STATUS[cycle_time] = "completed"

                log.info(f"JAR调用成功（周期{cycle_time}）：处理{user_num}台设备，生成{len(strategy_map)}个策略")
                return java_full_result
            else:
                log.error(f"JAR输出无JSON（周期{cycle_time}）：{result.stdout}")
        else:
            log.error(f"JAR执行失败（周期{cycle_time}）：\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")

    except Exception as e:
        log.error(f"JAR调用异常（周期{cycle_time}）：{str(e)}", exc_info=True)

    # 执行失败时更新状态
    with STORAGE_LOCK:
        CYCLE_STATUS[cycle_time] = "completed"
    return None


# 周期处理逻辑
async def run_cycle(cycle_time):
    """执行单个周期：调用JAR→存储策略"""
    STATE["last_cycle_start"] = datetime.now(AUS_TZ).isoformat()
    log.info(f"\n=== 周期启动：{cycle_time} ===")

    # 调用JAR模型
    await call_jar_model(cycle_time)

    STATE["last_cycle_end"] = datetime.now(AUS_TZ).isoformat()
    log.info(f"=== 周期结束：{cycle_time} ===")


# Flask接口
app = Flask(__name__)


# 用户注册页面
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
            return render_template("register.html")

        db = SessionLocal()
        try:
            existing_user = db.query(YstcUser).filter(YstcUser.username == data["username"]).first()
            if existing_user:
                return "用户名已存在，请更换后重试！"

            user_data = {
                "username": data["username"],
                "name": data["name"],
                "phone": data["phone"],
                "email": data["email"],
                "address": data["addr"],
                "password_hash": "default_hash_123",
            }
            new_user = YstcUser(**user_data)
            db.add(new_user)
            db.commit()
            log.info(f"用户注册成功：{data['username']}")
            return "注册成功！系统将启动2分钟周期循环。"
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
        return render_template("dashboard.html")
    return render_template("register.html")


# 设备上传接口
@app.route("/api/device/upload", methods=["POST"])
def upload_device_data():
    """设备上传完整数据"""
    try:
        req_data = request.get_json()
        device_id = str(req_data.get("device_id"))
        device_data = req_data.get("device_data")
        current_cycle = get_current_cycle()

        # 校验必要参数
        if not device_id or not device_data:
            return jsonify({
                "code": 400,
                "msg": "缺少device_id/device_data",
                "current_cycle": current_cycle
            }), 400

        # 检查上传窗口
        if not is_upload_window_open(current_cycle):
            with STORAGE_LOCK:
                cycle_status = CYCLE_STATUS.get(current_cycle, "unknown")
            return jsonify({
                "code": 403,
                "msg": f"上传窗口已关闭（状态：{cycle_status}）",
                "current_cycle": current_cycle
            }), 403

        # 存储设备数据
        with STORAGE_LOCK:
            DEVICE_DATA[current_cycle][device_id] = device_data

        log.info(f"设备[{device_id}]上传数据至周期[{current_cycle}]")
        return jsonify({
            "code": 200,
            "msg": "上传成功",
            "cycle_time": current_cycle,
            "device_id": device_id
        }), 200

    except Exception as e:
        log.error(f"设备上传失败：{str(e)}", exc_info=True)
        return jsonify({"code": 500, "msg": f"上传失败：{str(e)}"}), 500


# 设备查询策略接口
@app.route("/api/device/get_strategy", methods=["GET"])
def get_strategy():
    """查询设备策略"""
    try:
        device_id = request.args.get("device_id")
        cycle_time = request.args.get("cycle_time")

        if not device_id or not cycle_time:
            return jsonify({"code": 400, "msg": "缺少device_id/cycle_time"}), 400

        # 读取策略
        with STORAGE_LOCK:
            cycle_strategies = DEVICE_STRATEGIES.get(cycle_time, {})
            strategy = cycle_strategies.get(device_id)
            cycle_status = CYCLE_STATUS.get(cycle_time, "unknown")

        if not strategy:
            # 尝试按索引匹配（兼容JAR返回的索引）
            if device_id.isdigit():
                idx = int(device_id)
                strategy_list = list(cycle_strategies.values())
                if idx < len(strategy_list):
                    strategy = strategy_list[idx]

        if not strategy:
            return jsonify({
                "code": 404,
                "msg": "未找到策略",
                "cycle_status": cycle_status,
                "available_devices": list(cycle_strategies.keys())
            }), 404

        return jsonify({
            "code": 200,
            "device_id": device_id,
            "cycle_time": cycle_time,
            "strategy": strategy
        }), 200

    except Exception as e:
        log.error(f"策略查询失败：{str(e)}", exc_info=True)
        return jsonify({"code": 500, "msg": f"查询失败：{str(e)}"}), 500


# 健康检查接口
@app.route("/health")
def health():
    try:
        db = SessionLocal()
        db.query(YstcUser).first()
        db.close()
        STATE["db_status"] = "connected"
    except Exception as e:
        STATE["db_status"] = f"disconnected: {str(e)}"

    db = SessionLocal()
    STATE["user_file_seen"] = db.query(YstcUser).first() is not None
    db.close()

    # 当前周期信息
    current_cycle = get_current_cycle()
    with STORAGE_LOCK:
        current_dev_count = len(DEVICE_DATA.get(current_cycle, {}))
        current_cycle_status = CYCLE_STATUS.get(current_cycle, "unknown")

    STATE.update({
        "current_cycle": current_cycle,
        "current_cycle_status": current_cycle_status,
        "current_device_count": current_dev_count,
        "upload_window": UPLOAD_WINDOW,
        "cycle_interval": CYCLE_INTERVAL
    })

    return jsonify(STATE)


# 后台循环
async def service_loop():
    try:
        STATE["loop_started"] = True
        log.info("系统调控循环启动")

        # 等待用户注册
        db = SessionLocal()
        while not db.query(YstcUser).first():
            db.close()
            STATE["user_file_seen"] = False
            await asyncio.sleep(1)
            db = SessionLocal()
        db.close()
        STATE["user_file_seen"] = True
        log.info("检测到已注册用户，启动2分钟周期循环")

        # 初始化周期起始时间
        get_current_cycle.start_time = time.time()
        log.info(f"周期系统启动，基准时间：{datetime.fromtimestamp(get_current_cycle.start_time, tz=AUS_TZ)}")

        # 持续周期处理
        while True:
            current_cycle = get_current_cycle()
            cycle_start_ts = datetime.fromisoformat(current_cycle).timestamp()

            # 等待上传窗口结束
            upload_deadline = cycle_start_ts + UPLOAD_WINDOW
            current_ts = time.time()
            if current_ts < upload_deadline:
                wait_time = upload_deadline - current_ts
                log.info(f"周期[{current_cycle}]上传窗口开启，剩余{wait_time:.1f}秒")
                await asyncio.sleep(wait_time)

            # 强制执行博弈
            await run_cycle(current_cycle)

            # 清理过期数据
            clean_expired_data()

            # 等待下一个周期
            next_cycle_start_ts = cycle_start_ts + CYCLE_INTERVAL
            current_ts = time.time()
            if current_ts < next_cycle_start_ts:
                wait_time = next_cycle_start_ts - current_ts
                log.info(f"等待{wait_time:.1f}秒进入下一个周期")
                await asyncio.sleep(wait_time)

    except Exception as e:
        STATE["last_error"] = repr(e)
        log.exception("后台循环异常")


# 启动入口
def start_web_server():
    STATE["web_started"] = True
    log.info("启动Web服务（Flask）:8080")
    app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False, threaded=True)


def main():
    init_db()
    STATE["booted"] = True
    log.info("系统启动：初始化完成")
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()
    asyncio.run(service_loop())


if __name__ == "__main__":
    main()