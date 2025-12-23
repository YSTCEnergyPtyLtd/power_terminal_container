import asyncio, os, json, logging, threading
from datetime import datetime, timedelta
import pytz
from flask import Flask, request, render_template_string, jsonify
import aiohttp

# ===== 基本参数 =====
CN_TZ = pytz.timezone(os.getenv("TZ", "Asia/Shanghai"))
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
    """
    云端策略获取函数：
    """
    # API 通信配置
    API_CONFIG = {
        # 博弈端口配置
        "base_url": "http://119.13.125.115:5000",
        # 时间配置
        "request_interval": 2, # 根据需求调整
        "timeout": 20,
        # 重传配置
        "upload_retry_times": 3,
        "upload_retry_delay": 2,
        "strategy_retry_times": 3,
        "strategy_retry_delay": 3,
        # 等待博弈时间配置
        "wait_after_upload": 15
    }
    # 下面两个是需要从read_meter_data获取的数据
    # DEVICE_BASE_INFO & DEVICE_OPER_PARAMS数据从read_meter_data获取
    DEVICE_BASE_INFO = {
        "serial_number": "DEVICE-BAT-001",
        "id": 1,
        "type": "电池",
        "model": "BAT-100kWh",
        "working_power": 100.0
    }
    DEVICE_OPER_PARAMS = {
        "produce": [100.0, 90.0, 80.0],
        "currentStorage": [50.0, 50.0, 50.0],
        "demands": [20.0, 25.0, 18.0],
        "chargeSpeed": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        "chargeCost": [0.5, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.0, 0.1, 0.2],
        "dischargeSpeed": [8.0, 8.0, 8.0, 7.0, 7.0, 6.0, 6.0, 5.0, 5.0, 4.0],
        "dischargeCost": [0.3, 0.4, 0.3, 0.2, 0.1, 0.0, 0.1, 0.2, 0.3, 0.4],
        "overallCapacity": 100.0
    }
    # 兜底策略 可以根据需求调整
    FALLBACK_STRATEGY_RULE = {
        "threshold_power": 11,
        "charge_power": 3,
        "discharge_power": -3
    }

    # 使用全局 Session
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=10, keepalive_timeout=60),
        timeout=aiohttp.ClientTimeout(total=API_CONFIG["timeout"])
    ) as session:

        # 子函数1：检查周期+上传数据
        async def _check_cycle_and_upload(_upload_retry=0):
            await asyncio.sleep(API_CONFIG["request_interval"] / 2)
            try:
                # 检查 API 周期状态
                async with session.get(f"{API_CONFIG['base_url']}/api/cycle-status") as resp:
                    if resp.status != 200:
                        raise Exception(f"检查周期失败 | 状态码：{resp.status}")
                    cycle_status_data = await resp.json()

                latest_cycle = max(cycle_status_data["cycles"].keys()) if (
                        cycle_status_data.get("cycles") and isinstance(cycle_status_data["cycles"], dict)) else None
                if not latest_cycle:
                    raise Exception("服务器当前无可用周期")

                window_status = cycle_status_data["window_status"].get(latest_cycle, {})
                if not window_status.get("open", False):
                    raise Exception(f"周期 {latest_cycle} 上传窗口未开放")

                # 构建并上传设备数据
                device_data = {**DEVICE_BASE_INFO, **DEVICE_OPER_PARAMS}
                async with session.post(
                    f"{API_CONFIG['base_url']}/api/upload-device-data",
                    json={
                        "serial_number": DEVICE_BASE_INFO["serial_number"],
                        "device_data": device_data,
                        "cycle_time": latest_cycle
                    },
                    headers={"Content-Type": "application/json"}
                ) as upload_resp:
                    upload_json = await upload_resp.json()
                    if upload_resp.status != 200:
                        error_msg = upload_json.get("msg", "") or upload_json.get("error", "未知错误")
                        if upload_resp.status == 409:
                            raise Exception(f"设备已上传过数据| {error_msg}")
                        raise Exception(f"上传失败 | {error_msg}")
                log.info(f"设备 {DEVICE_BASE_INFO['serial_number']} 在周期 {latest_cycle} 数据上传成功！")
                return latest_cycle

            except Exception as e:
                if "已上传过数据" in str(e):
                    log.info(f"设备 {DEVICE_BASE_INFO['serial_number']} 已在周期上传过数据，终止重试")
                    return latest_cycle
                if _upload_retry < API_CONFIG["upload_retry_times"]:
                    log.warning(f"上传异常，重试第 {_upload_retry + 1} 次: {str(e)}")
                    await asyncio.sleep(API_CONFIG["upload_retry_delay"])
                    return await _check_cycle_and_upload(_upload_retry + 1)
                else:
                    raise Exception(f"上传重试 {API_CONFIG['upload_retry_times']} 次后仍失败: {str(e)}")

        # 子函数2：查询策略
        async def _query_strategy(cycle_time, _strategy_retry=0):
            try:
                async with session.get(
                    f"{API_CONFIG['base_url']}/api/get-strategy",
                    params={"serial_number": DEVICE_BASE_INFO["serial_number"], "cycle_time": cycle_time}
                ) as strategy_resp:
                    if strategy_resp.status == 200:
                        strategy_data = await strategy_resp.json()
                        log.info(f"获取设备 {DEVICE_BASE_INFO['serial_number']} 云端策略成功！")
                        return strategy_data.get("data", {})
                    else:
                        raise Exception(f"策略查询失败 | 状态码：{strategy_resp.status}")

            except Exception as e:
                if _strategy_retry < API_CONFIG["strategy_retry_times"]:
                    log.warning(f"策略查询异常，重试第 {_strategy_retry + 1} 次: {str(e)}")
                    await asyncio.sleep(API_CONFIG["strategy_retry_delay"])
                    return await _query_strategy(cycle_time, _strategy_retry + 1)
                else:
                    raise Exception(f"策略查询重试 {API_CONFIG['strategy_retry_times']} 次后仍失败: {str(e)}")

        # 主逻辑
        try:
            # 执行上传
            cycle_time = await _check_cycle_and_upload()
            # 等待云端计算
            await asyncio.sleep(API_CONFIG["wait_after_upload"])
            # 获取结果
            strategy = await _query_strategy(cycle_time)

            # ==================================================================
            # 返回的策略如图所示
            # {
            #     "cycle_time": "2025-12-20T17:45:00+08:00",
            #     "details": [
            #         {
            #             "action_type": "idle",
            #             "expected_benefit": 9.94,
            #             "power_setpoint": null,
            #             "reasoning": null,
            #             "time_point": "2025-12-20T17:45:00"
            #         },
            #         {
            #             "action_type": "charge",
            #             "expected_benefit": 9.94,
            #             "power_setpoint": 0.9,
            #             "reasoning": null,
            #             "time_point": "2025-12-20T18:00:00"
            #         },
            #         {
            #             "action_type": "idle",
            #             "expected_benefit": 9.94,
            #             "power_setpoint": null,
            #             "reasoning": null,
            #             "time_point": "2025-12-20T18:15:00"
            #         }
            #     ],
            #     "device_id": 14,
            #     "serial_number": "DEVICE-BAT-001",
            #     "status": "已生成",
            #     "strategy_id": 13,
            #     "strategy_name": "周期2025-12-20T17:45:00_用户test_user_001_博弈策略",
            #     "strategy_type": "博弈优化策略",
            #     "user_id": 11
            # }
            return strategy

        except Exception as e:
            log.error(f"云端策略获取流程失败：{str(e)}。切换至本地兜底策略。")
            fallback_strategy = {
                "action": "DISCHARGE" if predicted_power > FALLBACK_STRATEGY_RULE["threshold_power"] else "CHARGE",
                "power_kw": FALLBACK_STRATEGY_RULE["discharge_power"] if predicted_power > FALLBACK_STRATEGY_RULE[
                    "threshold_power"] else FALLBACK_STRATEGY_RULE["charge_power"]
            }
            return fallback_strategy

async def control_battery(strategy):
    log.info(f"执行策略：{strategy['action']}，功率 {strategy['power_kw']} kW")
    await asyncio.sleep(1)
    log.info("执行完成")



# ===== 整刻对时 =====
async def align_to_next_quarter():
    now = datetime.now(CN_TZ)
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
    STATE["last_cycle_start"] = datetime.now(CN_TZ).isoformat()
    log.info(f"=== 周期开始：{datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')} ===")
    meter = await read_meter_data()
    pred  = await forecast_power(meter)
    strat = await get_cloud_strategy(pred)
    await control_battery(strat)
    log.info(f"=== 周期结束：{datetime.now(CN_TZ).strftime('%H:%M:%S')} ===\n")
    STATE["last_cycle_end"] = datetime.now(CN_TZ).isoformat()

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
