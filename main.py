import asyncio, os, json, logging, threading
from datetime import datetime, timedelta
import pytz
from flask import Flask, request, render_template_string, jsonify

# ===== 基本参数 =====
AUS_TZ = pytz.timezone(os.getenv("TZ", "Australia/Melbourne"))
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
LOG_DIR  = os.getenv("LOG_DIR", "/app/logs")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

USER_FILE = os.path.join(DATA_DIR, "user_info.json")

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
    "last_cycle_start": None,
    "last_cycle_end": None,
    "next_quarter_wait_sec": None,
    "last_error": None,
}

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

# ===== Flask 页面 =====
FORM_HTML = """
<!doctype html>
<title>Power Terminal 注册</title>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<div style="max-width:520px;margin:32px auto;font-family:system-ui">
  <h2>站点注册</h2>
  <form method="post">
    <label>姓名</label><br><input name="name" required style="width:100%;padding:8px"><br><br>
    <label>用户ID</label><br><input name="user_id" required style="width:100%;padding:8px"><br><br>
    <label>手机号</label><br><input name="phone" required style="width:100%;padding:8px"><br><br>
    <label>Email</label><br><input type="email" name="email" required style="width:100%;padding:8px"><br><br>
    <label>地址</label><br><input name="addr" required style="width:100%;padding:8px"><br><br>
    <button style="padding:10px 16px">提交并启动</button>
  </form>
  <p style="margin-top:24px"><a href="/health">查看健康状态</a></p>
</div>
"""

REGISTERED_HTML = """
<!doctype html>
<title>Power Terminal 已注册</title>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<div style="max-width:520px;margin:32px auto;font-family:system-ui;text-align:center">
  <h2>✅ 已注册</h2>
  <p>此设备已完成注册并正在运行。</p>
  <form action="/reset" method="post">
    <button style="padding:10px 16px;background:#f44336;color:white;border:none;border-radius:6px">重置注册信息</button>
  </form>
  <p style="margin-top:24px"><a href="/health">查看健康状态</a></p>
</div>
"""

RESET_HTML = """
<!doctype html>
<title>Power Terminal 重置成功</title>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<div style="max-width:520px;margin:32px auto;font-family:system-ui;text-align:center">
  <h2>🔄 注册信息已清除</h2>
  <p>请 <a href="/">点击此处重新注册</a></p>
  <p style="margin-top:24px"><a href="/health">查看健康状态</a></p>
</div>
"""

app = Flask(__name__)

@app.route("/", methods=["GET","POST"])
def index():
    if request.method == "POST":
        data = {
            "name": request.form.get("name","").strip(),
            "user_id": request.form.get("user_id","").strip(),
            "phone": request.form.get("phone","").strip(),
            "email": request.form.get("email","").strip(),
            "addr": request.form.get("addr","").strip(),
        }
        if not all(data.values()):
            return render_template_string(FORM_HTML)
        with open(USER_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log.info(f"注册完成，写入 {USER_FILE}：{data}")
        return "注册成功！容器将进入15分钟整刻循环。可关闭此页面。"
    if os.path.exists(USER_FILE):
        return render_template_string(REGISTERED_HTML)
    return render_template_string(FORM_HTML)

@app.route("/reset", methods=["POST"])
def reset_registration():
    if os.path.exists(USER_FILE):
        os.remove(USER_FILE)
        log.info("用户请求：注册信息已重置。")
    return render_template_string(RESET_HTML)

@app.route("/health")
def health():
    # 实时刷新 user_file 是否存在
    STATE["user_file_seen"] = os.path.exists(USER_FILE)
    return jsonify(STATE)

# ===== 后台异步循环 =====
async def service_loop():
    try:
        STATE["loop_started"] = True
        log.info("系统（调控循环）启动")
        # 等待注册文件出现
        while not os.path.exists(USER_FILE):
            STATE["user_file_seen"] = False
            await asyncio.sleep(1)
        STATE["user_file_seen"] = True

        # 进入 15 分钟整刻循环
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
    STATE["booted"] = True
    log.info("BOOT: 进程启动，准备启动 Web 与后台循环")
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()
    asyncio.run(service_loop())

if __name__ == "__main__":
    main()
