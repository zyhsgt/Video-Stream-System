"""
完整功能验证脚本

验证步骤：
1. 检查API服务是否运行
2. 测试设备监控功能
3. 测试视频流推送（需要MediaMTX和FFMPEG）

使用方式：
    conda activate video-stream
    python -m backend.test_full_demo
"""

import os
import sys
import time

import requests

BASE_URL = "http://127.0.0.1:8000"

# 测试视频路径
TEST_VIDEO = os.path.join(
    os.path.dirname(__file__), 
    "..", "video_monitor", "test_video", "Fighting_2.mp4"
)


def check_api_running() -> bool:
    """检查API服务是否运行"""
    print("\n" + "=" * 50)
    print("📡 检查API服务状态")
    print("=" * 50)
    
    try:
        resp = requests.get(f"{BASE_URL}/", timeout=3)
        if resp.status_code == 200:
            print("✅ API服务正在运行")
            return True
    except Exception:
        pass
    
    print("❌ API服务未运行！")
    print("请先启动服务: python -m uvicorn backend.main:app --reload")
    return False


def test_device_monitoring() -> None:
    """测试设备监控功能"""
    print("\n" + "=" * 50)
    print("🔍 测试设备监控功能")
    print("=" * 50)
    
    # 1. Ping本地
    print("\n[1] 测试Ping本地 127.0.0.1")
    resp = requests.get(f"{BASE_URL}/api/device/ping/127.0.0.1", timeout=10)
    result = resp.json()
    print(f"    状态: {'✅ 在线' if result['online'] else '❌ 离线'}")
    
    # 2. 注册设备
    print("\n[2] 注册测试设备")
    data = {
        "ip": "192.168.1.100",
        "name": "测试摄像头-1",
        "rtsp_url": "rtsp://192.168.1.100:8554/live/stream",
        "description": "测试设备"
    }
    resp = requests.post(f"{BASE_URL}/api/device/register", json=data, timeout=5)
    if resp.status_code == 200:
        result = resp.json()
        print(f"    ✅ 设备注册成功，ID: {result['device_id']}")
    else:
        print(f"    ⚠️ 设备可能已注册: {resp.json()}")
    
    # 3. 获取设备列表
    print("\n[3] 获取设备列表")
    resp = requests.get(f"{BASE_URL}/api/device/list", timeout=5)
    result = resp.json()
    print(f"    ✅ 共有 {result['total']} 个已注册设备")
    for device in result['devices']:
        print(f"       - {device['name']} ({device['ip']})")
    
    # 4. 获取设备状态
    print("\n[4] 检测所有设备在线状态 (可能需要几秒...)")
    resp = requests.get(f"{BASE_URL}/api/device/status", timeout=30)
    result = resp.json()
    print(f"    ✅ 在线: {result['online_count']} / 离线: {result['offline_count']}")


def test_video_stream() -> None:
    """测试视频流推送功能"""
    print("\n" + "=" * 50)
    print("🎬 测试视频流推送功能")
    print("=" * 50)
    
    # 检查测试视频是否存在
    video_path = os.path.abspath(TEST_VIDEO)
    if not os.path.exists(video_path):
        print(f"❌ 测试视频不存在: {video_path}")
        return
    
    print(f"📹 使用测试视频: {os.path.basename(video_path)}")
    
    # 1. 启动视频流
    print("\n[1] 启动视频流推送")
    data = {
        "video_path": video_path,
        "stream_name": "test_camera"
    }
    resp = requests.post(f"{BASE_URL}/api/stream/start", json=data, timeout=10)
    
    if resp.status_code == 200:
        result = resp.json()
        rtsp_url = result['rtsp_url']
        print(f"    ✅ 推流启动成功!")
        print(f"    📺 RTSP地址: {rtsp_url}")
    elif resp.status_code == 500 and "FFMPEG" in resp.text:
        print("    ❌ FFMPEG未安装，请先安装FFMPEG")
        print("    下载地址: https://ffmpeg.org/download.html")
        return
    else:
        error = resp.json().get('detail', resp.text)
        if "已在运行" in error:
            print("    ⚠️ 流已在运行")
            rtsp_url = "rtsp://127.0.0.1:8554/live/test_camera"
        else:
            print(f"    ❌ 启动失败: {error}")
            return
    
    # 2. 查看活跃流列表
    print("\n[2] 查看活跃流列表")
    resp = requests.get(f"{BASE_URL}/api/stream/list", timeout=5)
    result = resp.json()
    print(f"    ✅ 当前有 {result['count']} 个活跃流")
    for stream in result['streams']:
        print(f"       - {stream['name']}: {stream['rtsp_url']}")
    
    # 3. 等待一下让流稳定
    print("\n[3] 等待流稳定 (3秒)...")
    time.sleep(3)
    
    # 4. 尝试捕获帧
    print("\n[4] 尝试捕获视频帧")
    try:
        resp = requests.post(
            f"{BASE_URL}/api/stream/capture",
            json={"rtsp_url": rtsp_url},
            timeout=15
        )
        if resp.status_code == 200:
            result = resp.json()
            print(f"    ✅ 成功捕获帧! 尺寸: {result['width']}x{result['height']}")
            print(f"    📷 Base64长度: {len(result['frame'])} 字符")
        else:
            print(f"    ❌ 捕获失败: {resp.json().get('detail', 'Unknown error')}")
            print("    提示: 请确保MediaMTX正在运行")
    except Exception as e:
        print(f"    ❌ 捕获超时或失败: {e}")
        print("    提示: 请确保MediaMTX正在运行 (端口8554)")
    
    # 5. 停止流
    print("\n[5] 停止视频流")
    resp = requests.post(
        f"{BASE_URL}/api/stream/stop",
        json={"stream_name": "test_camera"},
        timeout=10
    )
    if resp.status_code == 200:
        print("    ✅ 流已停止")
    else:
        print(f"    ⚠️ {resp.json().get('detail', 'Unknown')}")


def main() -> None:
    """主函数"""
    print("\n" + "🚀" * 20)
    print("  RTSP视频流模拟系统 - 功能验证")
    print("🚀" * 20)
    
    # 检查服务状态
    if not check_api_running():
        sys.exit(1)
    
    # 测试设备监控
    test_device_monitoring()
    
    # 询问是否测试视频流
    print("\n" + "=" * 50)
    print("💡 视频流测试需要:")
    print("   1. MediaMTX 运行中 (端口8554)")
    print("   2. FFMPEG 已安装")
    print("=" * 50)
    
    answer = input("\n是否测试视频流推送? (y/n): ").strip().lower()
    if answer == 'y':
        test_video_stream()
    else:
        print("跳过视频流测试")
    
    print("\n" + "✨" * 20)
    print("  验证完成!")
    print("✨" * 20 + "\n")


if __name__ == "__main__":
    main()
