"""
简单 HTTP 测试脚本，用于验证 backend 中 FastAPI 接口是否可正常被调用。

使用方式：
1. 确保你已经在本地启动了 FastAPI 服务，例如：
   uvicorn main:app --reload
   或根据你的项目实际入口修改。
2. 在项目根目录下执行：
   python -m backend.test_api_http
"""

import sys
from typing import Optional

import requests


def test_hello_world(base_url: str) -> None:
    """测试 /api/device/hello 接口是否可用。"""
    url = f"{base_url}/api/device/hello"
    print(f"[*] 测试接口: GET {url}")
    try:
        resp = requests.get(url, timeout=5)
        print("[*] 状态码:", resp.status_code)
        print("[*] 响应内容:", resp.json())
    except Exception as exc:  # noqa: BLE001
        print("[!] 调用 /api/device/hello 失败:", repr(exc))


def test_stream_api(base_url: str) -> None:
    """测试视频流相关接口。"""
    print("\n=== 测试视频流 API ===")
    
    # 测试接口可用性
    url = f"{base_url}/api/stream/test"
    print(f"[*] 测试接口: GET {url}")
    try:
        resp = requests.get(url, timeout=5)
        print("[*] 状态码:", resp.status_code)
        print("[*] 响应内容:", resp.json())
    except Exception as exc:
        print("[!] 调用失败:", repr(exc))
    
    # 获取流列表
    url = f"{base_url}/api/stream/list"
    print(f"\n[*] 测试接口: GET {url}")
    try:
        resp = requests.get(url, timeout=5)
        print("[*] 状态码:", resp.status_code)
        print("[*] 响应内容:", resp.json())
    except Exception as exc:
        print("[!] 调用失败:", repr(exc))


def test_device_monitor(base_url: str) -> None:
    """测试设备监控相关接口。"""
    print("\n=== 测试设备监控 API ===")
    
    # 测试ping本地
    url = f"{base_url}/api/device/ping/127.0.0.1"
    print(f"[*] 测试接口: GET {url}")
    try:
        resp = requests.get(url, timeout=10)
        print("[*] 状态码:", resp.status_code)
        print("[*] 响应内容:", resp.json())
    except Exception as exc:
        print("[!] 调用失败:", repr(exc))
    
    # 获取设备列表
    url = f"{base_url}/api/device/list"
    print(f"\n[*] 测试接口: GET {url}")
    try:
        resp = requests.get(url, timeout=5)
        print("[*] 状态码:", resp.status_code)
        print("[*] 响应内容:", resp.json())
    except Exception as exc:
        print("[!] 调用失败:", repr(exc))
    
    # 获取设备状态
    url = f"{base_url}/api/device/status"
    print(f"\n[*] 测试接口: GET {url}")
    try:
        resp = requests.get(url, timeout=30)
        print("[*] 状态码:", resp.status_code)
        print("[*] 响应内容:", resp.json())
    except Exception as exc:
        print("[!] 调用失败:", repr(exc))


def test_start_stream(base_url: str, video_path: str, stream_name: str = "camera1") -> None:
    """测试启动视频流推送。"""
    print("\n=== 测试启动视频流 ===")
    url = f"{base_url}/api/stream/start"
    data = {
        "video_path": video_path,
        "stream_name": stream_name
    }
    print(f"[*] 测试接口: POST {url}")
    print(f"[*] 请求数据: {data}")
    try:
        resp = requests.post(url, json=data, timeout=10)
        print("[*] 状态码:", resp.status_code)
        print("[*] 响应内容:", resp.json())
    except Exception as exc:
        print("[!] 调用失败:", repr(exc))


def test_register_device(base_url: str) -> None:
    """测试注册设备。"""
    print("\n=== 测试注册设备 ===")
    url = f"{base_url}/api/device/register"
    data = {
        "ip": "127.0.0.1",
        "name": "本地测试设备",
        "rtsp_url": "rtsp://127.0.0.1:8554/live/camera1",
        "description": "本地测试用摄像头模拟器"
    }
    print(f"[*] 测试接口: POST {url}")
    print(f"[*] 请求数据: {data}")
    try:
        resp = requests.post(url, json=data, timeout=5)
        print("[*] 状态码:", resp.status_code)
        print("[*] 响应内容:", resp.json())
    except Exception as exc:
        print("[!] 调用失败:", repr(exc))


def main() -> None:
    """
    命令行执行入口。

    可选参数：
        python -m backend.test_api_http [base_url] [video_path]

    例如：
        python -m backend.test_api_http
        python -m backend.test_api_http http://127.0.0.1:8000
        python -m backend.test_api_http http://127.0.0.1:8000 "C:/path/to/video.mp4"
    """
    base_url = "http://127.0.0.1:8000"
    video_path = None

    if len(sys.argv) >= 2:
        base_url = sys.argv[1]
    
    if len(sys.argv) >= 3:
        video_path = sys.argv[2]

    print(f"[*] 使用 base_url = {base_url}")

    print("\n=== 测试 /api/device/hello ===")
    test_hello_world(base_url)
    
    # 测试视频流API
    test_stream_api(base_url)
    
    # 测试设备监控API
    test_device_monitor(base_url)
    
    # 测试注册设备
    test_register_device(base_url)
    
    # 如果提供了视频路径，测试启动流
    if video_path:
        test_start_stream(base_url, video_path)


if __name__ == "__main__":
    main()

