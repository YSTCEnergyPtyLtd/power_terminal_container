import asyncio, os, json, logging, threading
from datetime import datetime, timedelta
import pytz
from flask import Flask, request, render_template_string, jsonify
import aiohttp
import random

# ===== 基本参数 =====
CN_TZ = pytz.timezone(os.getenv("TZ", "Asia/Shanghai"))

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.getenv("DATA_DIR", SCRIPT_DIR)
LOG_DIR  = os.getenv("LOG_DIR", os.path.join(SCRIPT_DIR, "logs"))
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

USER_FILE = os.path.join(SCRIPT_DIR, "user_info.json")

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

# ===== 核心任务 =====
# Modbus 寄存器地址 - 读取
BATT_VOLT   = 0x120C
BATT_CURR   = 0x120E
BATT_POWER  = 0x1210
BATT_SOC    = 0x1212
BATT_TIME   = 0x1214

# Modbus 寄存器地址 - 控制
WORK_MODE   = 0x300C
CTRL_MODE   = 0x304A
CTRL_POWER  = 0x304C

# Modbus 工具函数
def float_to_regs(v):
    import struct
    bs = struct.pack(">f", float(v))
    return [(bs[0]<<8)|bs[1], (bs[2]<<8)|bs[3]]

def regs_to_float(regs):
    b0=(regs[0]>>8)&0xFF; b1=regs[0]&0xFF
    b2=(regs[1]>>8)&0xFF; b3=regs[1]&0xFF
    import struct
    return struct.unpack(">f", bytes([b0,b1,b2,b3]))[0]

def read_f32(client, addr, slave=1):
    rr = client.read_holding_registers(address=addr, count=2, slave=slave)
    return regs_to_float(rr.registers)

def write_f32(client, addr, val, slave=1):
    regs = float_to_regs(val)
    client.write_registers(address=addr, values=regs, slave=slave)

async def read_meter_data():
    """读取电表数据（通过Modbus串口）"""
    from pymodbus.client import ModbusSerialClient
    import csv
    
    client = ModbusSerialClient(
        port="/dev/ttyUSB0",
        baudrate=115200,
        timeout=1,
        parity="N",
        stopbits=1,
        bytesize=8
    )
    
    if not client.connect():
        log.error("Modbus串口连接失败")
        raise Exception("Modbus串口连接失败")
    
    try:
        # 读取电池数据
        voltage = read_f32(client, BATT_VOLT)
        current = read_f32(client, BATT_CURR)
        power = read_f32(client, BATT_POWER)
        soc = read_f32(client, BATT_SOC)
        backup_time = read_f32(client, BATT_TIME)
        
        log.info(f"读取电表数据成功: 电压={voltage:.2f}V, 电流={current:.2f}A, 功率={power:.2f}kW, SOC={soc:.1f}%")
        
        # 保存到CSV日志文件
        csv_file = os.path.join(SCRIPT_DIR, "meter_data_log.csv")
        file_exists = os.path.exists(csv_file)
        
        with open(csv_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # 如果文件不存在，写入表头
            if not file_exists:
                writer.writerow(["timestamp", "voltage_V", "current_A", "power_kW", "SOC_percent", "backup_time_h"])
            # 写入数据
            timestamp = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
            writer.writerow([timestamp, f"{voltage:.3f}", f"{current:.3f}", f"{power:.3f}", f"{soc:.2f}", f"{backup_time:.3f}"])
        
        return {
            "power_kw": power,
            "voltage_v": voltage,
            "current_a": current,
            "soc_percent": soc,
            "backup_time_h": backup_time
        }
    except Exception as e:
        log.error(f"读取Modbus数据失败: {str(e)}")
        raise
    finally:
        client.close()

async def forecast_power(meter_data):
    log.info("预测下一时段用电量（模拟）")
    await asyncio.sleep(1)
    test_forecast_power = [random.randint(0, 10) for _ in range(3)]
    return test_forecast_power


async def get_cloud_strategy(predicted_power,meter_data):
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
        "model": "BAT-10kWh",
        "working_power": 10.0
    }
    DEVICE_OPER_PARAMS = {
        "produce": [0, 0, 0],
        "currentStorage": [meter_data["soc_percent"], meter_data["soc_percent"], meter_data["soc_percent"]],
        "demands": predicted_power,
        "chargeSpeed": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        "chargeCost": [0.1, 0.1, 0.2, 0.2, 0.2, 0.3, 0.3, 0.3, 0.4, 0.4],
        "dischargeSpeed": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        "dischargeCost": [0.1, 0.2, 0.3, 0.4, 0.5, 0.4, 0.3, 0.3, 0.4, 0.8],
        "overallCapacity": 100.0
    }
    # 兜底策略 可以根据需求调整
    FALLBACK_STRATEGY_RULE = {
        "threshold_power": 10,
        "charge_power": 5,
        "discharge_power": -3
    }
    print("DEVICE_OPER_PARAMS:",DEVICE_OPER_PARAMS)
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
    """根据云端策略控制电池充放电"""
    from pymodbus.client import ModbusSerialClient
    
    # 提取第一个action
    if 'details' in strategy and len(strategy['details']) > 0:
        first_action = strategy['details'][0]
        action_type = first_action.get('action_type', 'idle')
        power_setpoint = first_action.get('power_setpoint', 0.0)
    else:
        # 兜底策略格式
        action_type = strategy.get('action', 'idle').lower()
        power_setpoint = abs(strategy.get('power_kw', 0.0))
    
    log.info(f"执行策略：{action_type}，功率设定 {power_setpoint} kW")
    
    try:
        client = ModbusSerialClient(
            port="/dev/ttyUSB0",
            baudrate=115200,
            timeout=1,
            parity="N",
            stopbits=1,
            bytesize=8
        )
        
        if not client.connect():
            log.error("Modbus串口连接失败，无法执行控制")
            return
        
        try:
            # 根据action_type设置工作模式
            if action_type == 'charge':
                # 充电模式：使用手动控制模式
                write_f32(client, WORK_MODE, 4.0)
                ctrl_mode = 1.0  # 充电模式
                ctrl_power = float(power_setpoint) if power_setpoint else 0.0
                
                # 写入控制寄存器
                write_f32(client, CTRL_POWER, ctrl_power)
                write_f32(client, CTRL_MODE, ctrl_mode)
                
                log.info(f"设置手动控制模式 - 充电，功率 {ctrl_power} kW")
                
            else:  # discharge 或 idle
                # 放电或闲置：切换到自发自用模式
                write_f32(client, WORK_MODE, 0.0)
                log.info(f"设置自发自用模式 (action: {action_type})")
            
            log.info("控制指令已发送")
            
        finally:
            client.close()
            
    except Exception as e:
        log.error(f"电池控制失败: {str(e)}")
        raise



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
    strat = await get_cloud_strategy(pred,meter)
    print("Cloud Strategy:",strat)
    await control_battery(strat)
    log.info(f"=== 周期结束：{datetime.now(CN_TZ).strftime('%H:%M:%S')} ===\n")
    STATE["last_cycle_end"] = datetime.now(CN_TZ).isoformat()

# ===== Flask 页面 =====
FORM_HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"/>
    <title>Power Terminal 设备注册</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        
        .container {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            padding: 40px;
            max-width: 520px;
            width: 100%;
            animation: slideIn 0.5s ease-out;
        }
        
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(-30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        h2 {
            color: #333;
            margin-bottom: 30px;
            text-align: center;
            font-size: 28px;
            font-weight: 600;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        label {
            display: block;
            color: #555;
            font-weight: 500;
            margin-bottom: 8px;
            font-size: 14px;
        }
        
        input {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 15px;
            transition: all 0.3s ease;
            background: white;
        }
        
        input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        
        input:hover {
            border-color: #b0b0b0;
        }
        
        button {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            margin-top: 10px;
        }
        
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 25px rgba(102, 126, 234, 0.4);
        }
        
        button:active {
            transform: translateY(0);
        }
        
        .footer-link {
            text-align: center;
            margin-top: 24px;
        }
        
        .footer-link a {
            color: #667eea;
            text-decoration: none;
            font-weight: 500;
            transition: color 0.3s ease;
        }
        
        .footer-link a:hover {
            color: #764ba2;
            text-decoration: underline;
        }
        
        .device-info {
            background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        
        .device-info p {
            color: #555;
            font-size: 13px;
            line-height: 1.6;
        }
    </style>
</head>
<body>
    <div class="container">
        <h2>🔋 设备注册</h2>
        <div class="device-info">
            <p>请填写设备信息以完成注册。所有信息将保存在本地配置文件中。</p>
        </div>
        <form method="post">
            <div class="form-group">
                <label>设备序列号 (Device Serial Number)</label>
                <input name="serial_number" placeholder="例如: DEVICE-BAT-001" required>
            </div>
            <div class="form-group">
                <label>姓名</label>
                <input name="name" placeholder="请输入您的姓名" required>
            </div>
            <div class="form-group">
                <label>用户ID</label>
                <input name="user_id" placeholder="请输入用户ID" required>
            </div>
            <div class="form-group">
                <label>手机号</label>
                <input name="phone" type="tel" placeholder="请输入手机号码" required>
            </div>
            <div class="form-group">
                <label>Email</label>
                <input type="email" name="email" placeholder="example@email.com" required>
            </div>
            <div class="form-group">
                <label>地址</label>
                <input name="addr" placeholder="请输入详细地址" required>
            </div>
            <button type="submit">提交并启动系统</button>
        </form>
        <div class="footer-link">
            <a href="/health">📊 查看系统健康状态</a>
        </div>
    </div>
</body>
</html>
"""

REGISTERED_HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"/>
    <title>Power Terminal 已注册</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        
        .container {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            padding: 40px;
            max-width: 520px;
            width: 100%;
            text-align: center;
            animation: slideIn 0.5s ease-out;
        }
        
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(-30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        h2 {
            color: #333;
            margin-bottom: 20px;
            font-size: 28px;
            font-weight: 600;
        }
        
        p {
            color: #666;
            margin-bottom: 30px;
            font-size: 16px;
            line-height: 1.6;
        }
        
        button {
            padding: 14px 24px;
            background: linear-gradient(135deg, #f44336 0%, #e91e63 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 25px rgba(244, 67, 54, 0.4);
        }
        
        button:active {
            transform: translateY(0);
        }
        
        .footer-link {
            margin-top: 24px;
        }
        
        .footer-link a {
            color: #667eea;
            text-decoration: none;
            font-weight: 500;
            transition: color 0.3s ease;
        }
        
        .footer-link a:hover {
            color: #764ba2;
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <h2>✅ 设备已注册</h2>
        <p>此设备已完成注册并正在运行。如需重新配置，请点击下方按钮重置注册信息。</p>
        <form action="/reset" method="post">
            <button type="submit">🔄 重置注册信息</button>
        </form>
        <div class="footer-link">
            <a href="/health">📊 查看系统健康状态</a>
        </div>
    </div>
</body>
</html>
"""

RESET_HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"/>
    <title>Power Terminal 重置成功</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        
        .container {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            padding: 40px;
            max-width: 520px;
            width: 100%;
            text-align: center;
            animation: slideIn 0.5s ease-out;
        }
        
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(-30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        h2 {
            color: #333;
            margin-bottom: 20px;
            font-size: 28px;
            font-weight: 600;
        }
        
        p {
            color: #666;
            margin-bottom: 30px;
            font-size: 16px;
            line-height: 1.6;
        }
        
        a {
            display: inline-block;
            padding: 14px 24px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-decoration: none;
            border-radius: 10px;
            font-size: 16px;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        
        a:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 25px rgba(102, 126, 234, 0.4);
        }
        
        a:active {
            transform: translateY(0);
        }
        
        .footer-link {
            margin-top: 24px;
        }
        
        .footer-link a {
            display: inline;
            padding: 0;
            background: none;
            color: #667eea;
            font-size: 14px;
            box-shadow: none;
        }
        
        .footer-link a:hover {
            color: #764ba2;
            text-decoration: underline;
            transform: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <h2>🔄 注册信息已清除</h2>
        <p>系统已成功重置。请重新注册设备以继续使用。</p>
        <a href="/">🔋 重新注册设备</a>
        <div class="footer-link">
            <a href="/health">📊 查看系统健康状态</a>
        </div>
    </div>
</body>
</html>
"""

app = Flask(__name__)

@app.route("/", methods=["GET","POST"])
def index():
    if request.method == "POST":
        data = {
            "serial_number": request.form.get("serial_number","").strip(),
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
        return """
<!doctype html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"/>
    <title>注册成功</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            padding: 40px;
            max-width: 520px;
            width: 100%;
            text-align: center;
            animation: slideIn 0.5s ease-out;
        }
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(-30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        h2 {
            color: #333;
            margin-bottom: 20px;
            font-size: 28px;
            font-weight: 600;
        }
        p {
            color: #666;
            font-size: 16px;
            line-height: 1.6;
        }
        .success-icon {
            font-size: 64px;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="success-icon">✅</div>
        <h2>注册成功！</h2>
        <p>设备已成功注册。系统将进入15分钟整刻循环模式。</p>
        <p style="margin-top: 20px; color: #999; font-size: 14px;">您可以安全地关闭此页面。</p>
    </div>
</body>
</html>
        """
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

# ===== 数据记录循环（每秒）=====
async def data_logging_loop():
    """每秒读取并记录电表数据"""
    try:
        log.info("系统（数据记录循环）启动")
        # 等待注册文件出现
        while not os.path.exists(USER_FILE):
            await asyncio.sleep(1)
        
        log.info("开始每秒记录电表数据...")
        while True:
            try:
                await read_meter_data()
                await asyncio.sleep(1)
            except Exception as e:
                log.error(f"数据记录异常: {str(e)}")
                await asyncio.sleep(5)  # 出错后等待5秒再重试
    except Exception as e:
        STATE["last_error"] = repr(e)
        log.exception("数据记录循环异常")

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
    log.info("启动 Web 注册服务 (Flask) on :8000")
    app.run(host="0.0.0.0", port=8000, debug=False, use_reloader=False, threaded=True)

def main():
    STATE["booted"] = True
    log.info("BOOT: 进程启动，准备启动 Web 与后台循环")
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()
    
    # 并发运行数据记录循环和策略执行循环
    async def run_all():
        await asyncio.gather(
            data_logging_loop(),
            service_loop()
        )
    
    asyncio.run(run_all())

if __name__ == "__main__":
    main()
