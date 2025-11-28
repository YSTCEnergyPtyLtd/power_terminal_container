from locust import HttpUser, task, between, SequentialTaskSet
import random
import json

# 压测配置
SERVER_IP = "119.13.125.115"  # IP地址
SERVER_PORT = 5002  # 服务器接口端口
SIMULATE_DEVICE_COUNT = 100  # 模拟设备数量
REQUEST_INTERVAL = (0.05, 0.1)  # 每个设备的请求间隔（秒）：0.05-0.1秒/次 10-20 QPS/设备

# 构造模拟设备ID列表（避免重复，模拟真实多设备）
DEVICE_IDS = [f"locust_device_{i:06d}" for i in range(1, SIMULATE_DEVICE_COUNT + 1)]


# 压测任务集
class TestUploadTaskSet(SequentialTaskSet):
    @task(10)  # 任务权重：10（核心任务）
    def upload_test_data(self):
        """模拟设备上传测试数据（核心压测接口）"""
        # 随机生成请求参数（符合接口要求）
        payload = {
            "device_id": random.choice(DEVICE_IDS),  # 随机选一个设备ID
            "test_data": round(random.uniform(10.0, 1000.0), 2)  # 随机测试数据（10-1000之间）
        }

        # 发送POST请求
        self.client.post(
            url="/api/test/upload",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            name="测试数据上传接口"  # Locust Web界面中显示的任务名称
        )

    @task(1)  # 任务权重：1（辅助任务）
    def health_check(self):
        """偶尔执行健康检查（模拟真实场景的少量附加请求）"""
        self.client.get(url="/health", name="服务健康检查")


# 压测用户类
class TestUploadUser(HttpUser):
    tasks = [TestUploadTaskSet]  # 任务集
    wait_time = between(*REQUEST_INTERVAL)  # 每个任务执行后的等待时间
    host = f"http://{SERVER_IP}:{SERVER_PORT}"  # 目标服务器地址


# 启动入口
if __name__ == "__main__":
    import os

    # 直接运行脚本时，自动调用Locust命令
    os.system(f"locust -f {__file__} --web-port 8089")