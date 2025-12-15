import sys
import os
import time
import random
import threading
import requests
import json
from datetime import datetime, timedelta
import pytz
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError  # 数据库异常处理

# 添加项目根目录到系统路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

# 项目模块导入
from config import config
from app.models import YstcUser, Device, GameStrategy, StrategyDetail

# 核心配置
BASE_URL = "http://127.0.0.1:8080"
TEST_CONFIG = {
    "user_count": 50,  # 测试用户数
    "create_thread_count": 3,  # 降低创建并发（解决MySQL连接数）
    "login_thread_count": 2,  # 登录并发
    "upload_thread_count": 5,  # 控制上传并发（避免窗口超时）
    "verify_thread_count": 1,  # 验证并发=1（解决连接数耗尽）
    "password": "Test@123456",  # 统一密码
    "cycle_wait_time": 30,  # 等待周期处理时间
    "timeout": 15,  # 延长超时
    "create_retry_times": 3,  # 创建重试次数
    "create_retry_delay": 2,  # 创建重试延迟
    "login_retry_times": 3,
    "login_retry_delay": 1,
    "upload_retry_times": 2,  # 上传重试次数（窗口内重试）
    "upload_retry_delay": 1,  # 上传重试延迟
    "verify_retry_times": 3,  # 验证重试次数
    "verify_retry_delay": 3,  # 验证重试延迟
    "request_interval": 0.2,  # 缩短请求间隔（加快上传）
    "mysql_retry_codes": [1040, 1213]  # 死锁错误码
}

# 统一时区
AUS_TZ = pytz.timezone(config.TZ if hasattr(config, 'TZ') else 'Australia/Melbourne')

# 前置清理
def clean_test_users():
    """清理之前测试残留的user_xxx格式用户"""
    try:
        engine = create_engine(
            config.SQLALCHEMY_DATABASE_URI,
            pool_size=5,
            max_overflow=10,
            pool_recycle=300
        )
        Session = sessionmaker(bind=engine)
        db = Session()

        # 删除user_xxx格式的测试用户及关联设备
        test_users = db.query(YstcUser).filter(YstcUser.username.like("user_%")).all()
        if test_users:
            user_ids = [u.id for u in test_users]
            db.query(Device).filter(Device.user_id.in_(user_ids)).delete(synchronize_session=False)
            db.query(YstcUser).filter(YstcUser.id.in_(user_ids)).delete(synchronize_session=False)
            db.commit()
            print(f"🗑️  清理残留测试用户：{len(test_users)}个，关联设备已删除")
        else:
            print("✅ 无残留测试用户")
    except Exception as e:
        print(f"⚠️  清理残留用户失败：{str(e)}")
    finally:
        db.close()

# 工具函数
def generate_user_info(index):
    """生成用户+设备注册信息"""
    username = f"user_{index:03d}"
    serial_number = f"SN{random.randint(10000000, 99999999)}{index:03d}"
    return {
        "username": username,
        "password": TEST_CONFIG["password"],
        "email": f"{username}@test.com",
        "phone": f"138{random.randint(10000000, 99999999)}",
        "address": f"Test Address {index}",
        "serial_number": serial_number,
        "device_name": f"Test Device {index}",
        "device_type": f"Type_{random.choice(['A', 'B', 'C'])}"
    }

def update_stats(key, count=1):
    """线程安全更新统计"""
    global result_stats
    with stats_lock:
        result_stats[key] += count

def create_single_user(user_info, retry_times=0):
    """创建用户（针对MySQL连接数错误重试）"""
    time.sleep(TEST_CONFIG["request_interval"])

    try:
        url = f"{BASE_URL}/api/device/register"
        res = requests.post(
            url,
            json=user_info,
            headers={"Content-Type": "application/json"},
            timeout=TEST_CONFIG["timeout"]
        )
        # 成功创建
        if res.status_code == 200 and res.json().get("code") == 200:
            update_stats("create_user_success")
            print(f"✅ 创建用户成功：{user_info['username']} | 设备SN：{user_info['serial_number']}")
            return user_info["username"], True

        # 解析错误信息
        res_json = res.json() if res.status_code != 500 else {}
        error_msg = res_json.get("msg", "")
        error_code = res_json.get("code", 0)

        # 针对MySQL连接数错误重试
        if retry_times < TEST_CONFIG["create_retry_times"]:
            if "1040" in error_msg or "Too many connections" in error_msg:
                print(f"⚠️ {user_info['username']} MySQL连接数耗尽，第{retry_times + 1}次重试...")
                time.sleep(TEST_CONFIG["create_retry_delay"] * (retry_times + 1))
                return create_single_user(user_info, retry_times + 1)
            elif error_code == 400 and "账号已存在" in error_msg:
                print(f"⚠️ {user_info['username']} 账号已存在，第{retry_times + 1}次重试...")
                new_user_info = generate_user_info(random.randint(1000, 9999))
                time.sleep(TEST_CONFIG["create_retry_delay"])
                return create_single_user(new_user_info, retry_times + 1)

        # 其他错误
        update_stats("create_user_fail")
        print(f"❌ 创建用户失败：{user_info['username']} | {res.text}")
        return user_info["username"], False

    except Exception as e:
        if retry_times < TEST_CONFIG["create_retry_times"]:
            print(f"⚠️ {user_info['username']} 创建异常，第{retry_times + 1}次重试... | {str(e)}")
            time.sleep(TEST_CONFIG["create_retry_delay"] * (retry_times + 1))
            return create_single_user(user_info, retry_times + 1)
        else:
            update_stats("create_user_fail")
            print(f"❌ 创建用户异常：{user_info['username']} | {str(e)}")
            return user_info["username"], False

def login_single_user(username, retry_times=0):
    """登录（含死锁/连接数重试）"""
    time.sleep(TEST_CONFIG["request_interval"] / 2)
    try:
        url = f"{BASE_URL}/api/device/login"
        res = requests.post(
            url,
            json={
                "username": username,
                "password": TEST_CONFIG["password"]
            },
            headers={"Content-Type": "application/json"},
            timeout=TEST_CONFIG["timeout"]
        )
        if res.status_code == 200 and res.json().get("code") == 200:
            access_token = res.json().get("access_token")
            update_stats("login_success")
            print(f"✅ 登录成功：{username} | Token：{access_token[:20]}...")
            return username, access_token, True
        else:
            error_msg = res.text
            if ("Deadlock found" in error_msg or "1040" in error_msg) and retry_times < TEST_CONFIG[
                "login_retry_times"]:
                print(f"⚠️ {username} 登录异常，第{retry_times + 1}次重试...")
                time.sleep(TEST_CONFIG["login_retry_delay"])
                return login_single_user(username, retry_times + 1)
            else:
                update_stats("login_fail")
                print(f"❌ 登录失败：{username} | {error_msg}")
                return username, None, False
    except Exception as e:
        if retry_times < TEST_CONFIG["login_retry_times"]:
            print(f"⚠️ {username} 登录异常，第{retry_times + 1}次重试... | {str(e)}")
            time.sleep(TEST_CONFIG["login_retry_delay"])
            return login_single_user(username, retry_times + 1)
        else:
            update_stats("login_fail")
            print(f"❌ 登录异常：{username} | {str(e)}")
            return username, None, False

def generate_device_data(device_id):
    """生成单台设备的完整参数"""
    overall_capacity = round(random.uniform(0.4, 2.0), 1)
    current_storage = [round(random.uniform(0.08, 1.3), 2) for _ in range(3)]
    demands = [round(random.uniform(0.08, 0.55), 2) for _ in range(3)]

    charge_speed = [round(random.uniform(0.05, 1.4), 2) for _ in range(10)]
    charge_cost = [round(random.uniform(0.005, 0.17), 3) for _ in range(10)]
    discharge_speed = [round(s + random.uniform(-0.05, 0.05), 2) for s in charge_speed]
    discharge_cost = [round(c + random.uniform(-0.005, 0.005), 3) for c in charge_cost]

    produce = None
    if device_id % 2 == 1:
        produce = [round(random.uniform(0.05, 0.2), 2) for _ in range(3)]

    device_data = {
        "id": device_id,
        "overallCapacity": overall_capacity,
        "currentStorage": current_storage,
        "demands": demands,
        "chargeSpeed": charge_speed,
        "chargeCost": charge_cost,
        "dischargeSpeed": discharge_speed,
        "dischargeCost": discharge_cost
    }
    if produce:
        device_data["produce"] = produce

    return device_data

def upload_single_device_data(username, access_token, device_id, retry_times=0):
    """上传设备数据（上传窗口关闭重试）"""
    time.sleep(TEST_CONFIG["request_interval"] / 2)
    try:
        # 获取当前周期
        cycle_url = f"{BASE_URL}/api/device/current_cycle"
        cycle_res = requests.get(
            cycle_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            timeout=TEST_CONFIG["timeout"]
        )
        if cycle_res.status_code != 200:
            if retry_times < TEST_CONFIG["upload_retry_times"]:
                print(f"⚠️ {username} 获取周期失败，第{retry_times + 1}次重试...")
                time.sleep(TEST_CONFIG["upload_retry_delay"])
                return upload_single_device_data(username, access_token, device_id, retry_times + 1)
            update_stats("upload_fail")
            print(f"❌ {username} 获取周期失败 | {cycle_res.text}")
            return username, None, False
        cycle_time = cycle_res.json().get("current_cycle")

        # 生成设备数据
        device_data = generate_device_data(device_id)
        print(f"📤 {username} 上传设备数据：ID={device_id} | 周期={cycle_time[:20]}...")

        # 上传数据
        upload_url = f"{BASE_URL}/api/device/upload"
        upload_res = requests.post(
            upload_url,
            json={"device_data": device_data},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            timeout=TEST_CONFIG["timeout"]
        )

        # 处理上传结果
        if upload_res.status_code == 200 and upload_res.json().get("code") == 200:
            update_stats("upload_success")
            print(f"✅ {username} 数据上传成功 | 周期：{cycle_time[:20]}")
            return username, cycle_time, True
        else:
            upload_json = upload_res.json() if upload_res.status_code != 500 else {}
            error_msg = upload_json.get("msg", "")

            # 上传窗口关闭时重试1次
            if "上传窗口已关闭" in error_msg and retry_times < TEST_CONFIG["upload_retry_times"]:
                print(f"⚠️ {username} 上传窗口关闭，第{retry_times + 1}次重试...")
                time.sleep(TEST_CONFIG["upload_retry_delay"])
                return upload_single_device_data(username, access_token, device_id, retry_times + 1)

            update_stats("upload_fail")
            print(f"❌ {username} 数据上传失败 | {upload_res.text}")
            return username, None, False
    except Exception as e:
        if retry_times < TEST_CONFIG["upload_retry_times"]:
            print(f"⚠️ {username} 上传异常，第{retry_times + 1}次重试... | {str(e)}")
            time.sleep(TEST_CONFIG["upload_retry_delay"])
            return upload_single_device_data(username, access_token, device_id, retry_times + 1)
        else:
            update_stats("upload_fail")
            print(f"❌ {username} 上传异常 | {str(e)}")
            return username, None, False

# 验证数据库博弈结果函数
def verify_single_db_data(username, cycle_time):
    """验证数据库博弈结果（修复策略匹配+连接数+时区问题）"""
    # 重试逻辑封装
    def _verify():
        try:
            with db_lock:
                engine = create_engine(
                    config.SQLALCHEMY_DATABASE_URI,
                    pool_size=5,
                    max_overflow=10,
                    pool_recycle=300
                )
                Session = sessionmaker(bind=engine)
                db_session = Session()

                # 查询用户
                user = db_session.query(YstcUser).filter(YstcUser.username == username).first()
                if not user:
                    update_stats("db_verify_fail")
                    print(f"❌ {username} 用户不存在")
                    return False

                # 解析周期时间
                try:
                    # 清理时间格式
                    clean_cycle = cycle_time.rstrip('.').split('+')[0]
                    # 解析为带墨尔本时区的datetime
                    cycle_dt = datetime.fromisoformat(clean_cycle).replace(tzinfo=AUS_TZ)
                    # 扩大匹配范围（前后5分钟，兼容落库延迟）
                    start_dt = cycle_dt - timedelta(minutes=5)
                    end_dt = cycle_dt + timedelta(minutes=5)
                    print(f"🔍 {username} 验证调试：用户ID={user.id} | 周期={cycle_dt} | 匹配范围={start_dt}~{end_dt}")
                except Exception as e:
                    update_stats("db_verify_fail")
                    print(f"❌ {username} 周期时间解析失败：{str(e)} | 原始时间：{cycle_time}")
                    return False

                # 精准匹配策略
                # 改用start_time匹配
                strategy = db_session.query(GameStrategy).filter(
                    GameStrategy.user_id == user.id,
                    GameStrategy.start_time >= start_dt,
                    GameStrategy.start_time <= end_dt
                ).first()

                # 打印该用户所有策略，方便定位问题
                all_strategies = db_session.query(GameStrategy.id, GameStrategy.start_time).filter(
                    GameStrategy.user_id == user.id
                ).all()
                print(f"🔍 {username} 所有策略：{all_strategies}")

                if not strategy:
                    update_stats("db_verify_fail")
                    print(f"❌ {username} 无博弈策略 | 周期：{cycle_time[:20]}")
                    return False

                # 验证策略详情
                details_count = db_session.query(StrategyDetail).filter(
                    StrategyDetail.strategy_id == strategy.id
                ).count()

                if details_count >= 1:
                    update_stats("db_verify_success")
                    print(f"✅ {username} 博弈结果验证成功 | 策略ID：{strategy.id} | 详情数：{details_count}")
                    return True
                else:
                    update_stats("db_verify_fail")
                    print(f"❌ {username} 策略无详情 | 周期：{cycle_time[:20]}")
                    return False
        except Exception as e:
            raise e
        finally:
            if 'db_session' in locals():
                db_session.close()

    # 执行重试逻辑
    retries = 0
    while retries < TEST_CONFIG["verify_retry_times"]:
        try:
            result = _verify()
            return username, result
        except OperationalError as e:
            error_code = e.orig.args[0] if e.orig else 0
            if error_code in TEST_CONFIG["mysql_retry_codes"]:
                retries += 1
                print(f"⚠️ {username} 数据库错误（码：{error_code}），第{retries}次重试...")
                time.sleep(TEST_CONFIG["verify_retry_delay"] * retries)
                continue
            # 非重试错误，直接返回失败
            update_stats("db_verify_fail")
            print(f"❌ {username} 数据库验证异常 | {str(e)}")
            return username, False
        except Exception as e:
            update_stats("db_verify_fail")
            print(f"❌ {username} 数据库验证异常 | {str(e)}")
            return username, False

    # 超过重试次数
    update_stats("db_verify_fail")
    print(f"❌ {username} 验证重试{TEST_CONFIG['verify_retry_times']}次仍失败")
    return username, False

# 主流程
if __name__ == "__main__":
    # 初始化全局变量
    global result_stats, stats_lock, db_lock
    result_stats = {
        "create_user_success": 0,
        "create_user_fail": 0,
        "login_success": 0,
        "login_fail": 0,
        "upload_success": 0,
        "upload_fail": 0,
        "db_verify_success": 0,
        "db_verify_fail": 0
    }
    stats_lock = threading.Lock()
    db_lock = threading.Lock()

    # 前置清理
    print("=" * 80)
    print("🧹 前置清理：删除残留测试用户")
    print("=" * 80)
    clean_test_users()

    # 启动测试
    print("\n" + "=" * 80)
    print(f"🚀 批量测试启动 | 用户数：{TEST_CONFIG['user_count']} | 上传并发：{TEST_CONFIG['upload_thread_count']}")
    print("=" * 80)

    # 阶段1：批量创建用户
    print("\n📌 阶段1：创建用户（含设备注册）")
    user_list = [generate_user_info(i + 1) for i in range(TEST_CONFIG["user_count"])]
    success_users = []
    with ThreadPoolExecutor(max_workers=TEST_CONFIG["create_thread_count"]) as executor:
        futures = [executor.submit(create_single_user, user) for user in user_list]
        for future in as_completed(futures):
            username, is_success = future.result()
            if is_success:
                success_users.append(username)

    # 阶段2：批量登录
    print("\n📌 阶段2：用户登录（获取Token）")
    token_dict = {}
    with ThreadPoolExecutor(max_workers=TEST_CONFIG["login_thread_count"]) as executor:
        futures = [executor.submit(login_single_user, username) for username in success_users]
        for future in as_completed(futures):
            username, access_token, is_success = future.result()
            if is_success:
                token_dict[username] = access_token

    # 重试失败的登录
    failed_login = [u for u in success_users if u not in token_dict]
    if failed_login:
        print(f"\n⚠️  重试登录失败用户：{failed_login}")
        for username in failed_login:
            _, access_token, is_success = login_single_user(username)
            if is_success:
                token_dict[username] = access_token

    # 阶段3：批量上传设备数据
    print("\n📌 阶段3：上传设备数据（匹配博弈接口）")
    cycle_dict = {}
    with ThreadPoolExecutor(max_workers=TEST_CONFIG["upload_thread_count"]) as executor:
        futures = []
        for idx, (username, token) in enumerate(token_dict.items()):
            device_id = idx
            futures.append(executor.submit(upload_single_device_data, username, token, device_id))

        for future in as_completed(futures):
            username, cycle_time, is_success = future.result()
            if is_success:
                cycle_dict[username] = cycle_time

    # 阶段4：等待周期处理
    print(f"\n📌 阶段4：等待周期处理（{TEST_CONFIG['cycle_wait_time']}秒）")
    time.sleep(TEST_CONFIG["cycle_wait_time"])

    # 阶段5：验证数据库博弈结果
    print("\n📌 阶段5：验证数据库博弈结果")
    with ThreadPoolExecutor(max_workers=TEST_CONFIG["verify_thread_count"]) as executor:
        futures = [executor.submit(verify_single_db_data, username, cycle_dict[username])
                   for username in cycle_dict.keys()]
        for future in as_completed(futures):
            future.result()

    # 输出测试报告
    print("\n" + "=" * 80)
    print("📊 测试报告汇总")
    print("=" * 80)
    total = TEST_CONFIG["user_count"]
    print(f"总用户数：{total}")
    print(
        f"用户创建成功率：{result_stats['create_user_success'] / total * 100:.2f}% ({result_stats['create_user_success']}/{total})")
    print(
        f"登录成功率：{result_stats['login_success'] / len(success_users) * 100:.2f}% ({result_stats['login_success']}/{len(success_users)})" if success_users else "登录成功率：0%")
    print(
        f"数据上传成功率：{result_stats['upload_success'] / len(token_dict) * 100:.2f}% ({result_stats['upload_success']}/{len(token_dict)})" if token_dict else "上传成功率：0%")
    print(
        f"博弈结果验证成功率：{result_stats['db_verify_success'] / len(cycle_dict) * 100:.2f}% ({result_stats['db_verify_success']}/{len(cycle_dict)})" if cycle_dict else "验证成功率：0%")
    print("=" * 80)
    print("🎉 批量测试完成！")