import requests
import threading
import json
import time

BASE_URL = "http://localhost:8080"
DEVICE_LIST = [
    {
        "id": 0,
        "overallCapacity": 0.8,
        "currentStorage": [0.2, 0.3, 0.1],
        "demands": [0.1, 0.2, 0.15],
        "chargeSpeed": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        "chargeCost": [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.1],
        "dischargeSpeed": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        "dischargeCost": [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.1]
    },
    {
        "id": 1,
        "overallCapacity": 1.5,
        "currentStorage": [0.5, 0.6, 0.4],
        "demands": [0.3, 0.4, 0.35],
        "produce": [0.12, 0.18, 0.15],
        "chargeSpeed": [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1],
        "chargeCost": [0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.1, 0.11],
        "dischargeSpeed": [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1],
        "dischargeCost": [0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.1, 0.11]
    },
    {
        "id": 2,
        "overallCapacity": 0.4,
        "currentStorage": [0.1, 0.15, 0.08],
        "demands": [0.08, 0.12, 0.1],
        "chargeSpeed": [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5],
        "chargeCost": [0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.035, 0.04, 0.045, 0.05],
        "dischargeSpeed": [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5],
        "dischargeCost": [0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.035, 0.04, 0.045, 0.05]
    },
    {
        "id": 3,
        "overallCapacity": 1.2,
        "currentStorage": [0.8, 0.3, 0.9],
        "demands": [0.2, 0.3, 0.25],
        "produce": [0.2, 0.05, 0.18],
        "chargeSpeed": [0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95, 1.05],
        "chargeCost": [0.015, 0.025, 0.035, 0.045, 0.055, 0.065, 0.075, 0.085, 0.095, 0.105],
        "dischargeSpeed": [0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95, 1.05],
        "dischargeCost": [0.015, 0.025, 0.035, 0.045, 0.055, 0.065, 0.075, 0.085, 0.095, 0.105]
    },
    {
        "id": 4,
        "overallCapacity": 2.0,
        "currentStorage": [1.2, 1.3, 1.2],
        "demands": [0.5, 0.55, 0.52],
        "chargeSpeed": [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3],
        "chargeCost": [0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.1, 0.11, 0.12, 0.13],
        "dischargeSpeed": [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3],
        "dischargeCost": [0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.1, 0.11, 0.12, 0.13]
    },
    {
        "id": 5,
        "overallCapacity": 0.6,
        "currentStorage": [0.2, 0.3, 0.4],
        "demands": [0.12, 0.15, 0.13],
        "produce": [0.15, 0.2, 0.18],
        "chargeSpeed": [0.12, 0.22, 0.32, 0.42, 0.52, 0.62, 0.72, 0.82, 0.92, 1.02],
        "chargeCost": [0.012, 0.022, 0.032, 0.042, 0.052, 0.062, 0.072, 0.082, 0.092, 0.102],
        "dischargeSpeed": [0.12, 0.22, 0.32, 0.42, 0.52, 0.62, 0.72, 0.82, 0.92, 1.02],
        "dischargeCost": [0.012, 0.022, 0.032, 0.042, 0.052, 0.062, 0.072, 0.082, 0.092, 0.102]
    },
    {
        "id": 6,
        "overallCapacity": 1.0,
        "currentStorage": [0.4, 0.5, 0.3],
        "demands": [0.2, 0.3, 0.18],
        "chargeSpeed": [0.18, 0.28, 0.38, 0.48, 0.58, 0.68, 0.78, 0.88, 0.98, 1.08],
        "chargeCost": [0.018, 0.028, 0.038, 0.048, 0.058, 0.068, 0.078, 0.088, 0.098, 0.108],
        "dischargeSpeed": [0.18, 0.28, 0.38, 0.48, 0.58, 0.68, 0.78, 0.88, 0.98, 1.08],
        "dischargeCost": [0.018, 0.028, 0.038, 0.048, 0.058, 0.068, 0.078, 0.088, 0.098, 0.108]
    },
    {
        "id": 7,
        "overallCapacity": 0.7,
        "currentStorage": [0.3, 0.4, 0.25],
        "demands": [0.15, 0.22, 0.18],
        "produce": [0.06, 0.09, 0.05],
        "chargeSpeed": [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4],
        "chargeCost": [0.08, 0.09, 0.1, 0.11, 0.12, 0.13, 0.14, 0.15, 0.16, 0.17],
        "dischargeSpeed": [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4],
        "dischargeCost": [0.08, 0.09, 0.1, 0.11, 0.12, 0.13, 0.14, 0.15, 0.16, 0.17]
    },
    {
        "id": 8,
        "overallCapacity": 1.8,
        "currentStorage": [1.0, 1.1, 0.9],
        "demands": [0.35, 0.4, 0.32],
        "chargeSpeed": [0.08, 0.15, 0.22, 0.29, 0.36, 0.43, 0.5, 0.57, 0.64, 0.71],
        "chargeCost": [0.008, 0.015, 0.022, 0.029, 0.036, 0.043, 0.05, 0.057, 0.064, 0.071],
        "dischargeSpeed": [0.08, 0.15, 0.22, 0.29, 0.36, 0.43, 0.5, 0.57, 0.64, 0.71],
        "dischargeCost": [0.008, 0.015, 0.022, 0.029, 0.036, 0.043, 0.05, 0.057, 0.064, 0.071]
    },
    {
        "id": 9,
        "overallCapacity": 1.1,
        "currentStorage": [0.6, 0.7, 0.5],
        "demands": [0.22, 0.28, 0.24],
        "produce": [0.1, 0.14, 0.12],
        "chargeSpeed": [0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95, 1.05, 1.15],
        "chargeCost": [0.025, 0.035, 0.045, 0.055, 0.065, 0.075, 0.085, 0.095, 0.105, 0.115],
        "dischargeSpeed": [0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95, 1.05, 1.15],
        "dischargeCost": [0.025, 0.035, 0.045, 0.055, 0.065, 0.075, 0.085, 0.095, 0.105, 0.115]
    }
]


def upload_device(device):
    device_id = str(device["id"])
    try:
        resp = requests.post(
            f"{BASE_URL}/api/device/upload",
            json={"device_id": device_id, "device_data": device},
            timeout=5
        )
        print(f"设备[{device_id}]上传结果：{resp.status_code} - {resp.json()['msg']}")
    except Exception as e:
        print(f"设备[{device_id}]上传失败：{e}")


def get_strategy(device_id, cycle_time):
    try:
        resp = requests.get(
            f"{BASE_URL}/api/device/get_strategy",
            params={"device_id": device_id, "cycle_time": cycle_time},
            timeout=5
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception as e:
        print(f"设备[{device_id}]策略查询失败：{e}")
        return None


if __name__ == "__main__":
    # 获取当前周期
    health_resp = requests.get(f"{BASE_URL}/health").json()
    current_cycle = health_resp["current_cycle"]
    print(f"当前周期：{current_cycle}")

    # 多线程上传10个设备
    threads = []
    for device in DEVICE_LIST:
        t = threading.Thread(target=upload_device, args=(device,))
        threads.append(t)
        t.start()

    # 等待所有上传完成
    for t in threads:
        t.join()

    # 等待博弈完成
    print("\n等待博弈计算...")
    while True:
        health_resp = requests.get(f"{BASE_URL}/health").json()
        if health_resp["current_cycle_status"] == "completed":
            break
        time.sleep(1)

    # 查询所有设备策略
    print("\n===== 设备策略结果 =====")
    for device in DEVICE_LIST:
        device_id = str(device["id"])
        strategy = get_strategy(device_id, current_cycle)
        if strategy:
            print(f"\n设备[{device_id}]：")
            print(f"  收益：{strategy['strategy']['benefit']}")
            print(f"  充放电指令：{strategy['strategy']['dc']}")
            print(f"  功率：{strategy['strategy']['speed']}")