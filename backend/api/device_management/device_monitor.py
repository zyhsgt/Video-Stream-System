"""
设备监控模块

功能：
- 检测设备是否在线（通过ping）
- 获取所有设备状态
- 注册/管理设备
"""

import json
import platform
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


router = APIRouter(prefix="/api/device", tags=["device_management"])

# 数据存储路径
DATA_DIR = Path(__file__).parent.parent.parent / "data"
DEVICES_FILE = DATA_DIR / "devices.json"


class RegisterDeviceRequest(BaseModel):
    """注册设备请求模型"""
    ip: str
    name: str
    rtsp_url: Optional[str] = None
    description: Optional[str] = None


class DeviceInfo(BaseModel):
    """设备信息模型"""
    id: int
    ip: str
    name: str
    rtsp_url: Optional[str] = None
    description: Optional[str] = None


def _ensure_data_dir() -> None:
    """确保数据目录存在"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_devices() -> dict:
    """加载设备配置"""
    _ensure_data_dir()
    if DEVICES_FILE.exists():
        with open(DEVICES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"devices": [], "next_id": 1}


def _save_devices(data: dict) -> None:
    """保存设备配置"""
    _ensure_data_dir()
    with open(DEVICES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _ping_host(ip: str, timeout: int = 2) -> bool:
    """
    Ping指定IP地址检测是否在线。
    
    Args:
        ip: 目标IP地址
        timeout: 超时时间（秒）
        
    Returns:
        是否在线
    """
    # 根据操作系统选择ping参数
    param = "-n" if platform.system().lower() == "windows" else "-c"
    timeout_param = "-w" if platform.system().lower() == "windows" else "-W"
    
    # Windows下-w参数单位是毫秒，Linux下是秒
    timeout_value = str(timeout * 1000) if platform.system().lower() == "windows" else str(timeout)
    
    command = ["ping", param, "1", timeout_param, timeout_value, ip]
    
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout + 1,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system().lower() == "windows" else 0
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


@router.get("/ping/{ip:path}")
async def ping_device(ip: str) -> dict:
    """
    检测设备是否在线。
    
    通过ping命令检测指定IP是否可达。
    
    Args:
        ip: 目标IP地址
        
    Returns:
        包含IP和在线状态的字典
    """
    online = _ping_host(ip)
    
    return {
        "ip": ip,
        "online": online,
        "message": "设备在线" if online else "设备离线"
    }


@router.get("/status")
async def get_all_device_status() -> dict:
    """
    获取所有已注册设备的状态。
    
    Returns:
        包含所有设备及其在线状态的字典
    """
    devices_data = _load_devices()
    devices_with_status = []
    
    for device in devices_data["devices"]:
        online = _ping_host(device["ip"])
        devices_with_status.append({
            "id": device["id"],
            "ip": device["ip"],
            "name": device["name"],
            "rtsp_url": device.get("rtsp_url"),
            "description": device.get("description"),
            "online": online
        })
    
    online_count = sum(1 for d in devices_with_status if d["online"])
    
    return {
        "devices": devices_with_status,
        "total": len(devices_with_status),
        "online_count": online_count,
        "offline_count": len(devices_with_status) - online_count
    }


@router.post("/register")
async def register_device(request: RegisterDeviceRequest) -> dict:
    """
    注册新设备。
    
    Args:
        request: 包含ip, name, rtsp_url, description的请求
        
    Returns:
        包含成功状态和设备ID的字典
    """
    devices_data = _load_devices()
    
    # 检查IP是否已注册
    existing = [d for d in devices_data["devices"] if d["ip"] == request.ip]
    if existing:
        raise HTTPException(status_code=400, detail=f"设备IP {request.ip} 已注册")
    
    # 创建新设备
    new_device = {
        "id": devices_data["next_id"],
        "ip": request.ip,
        "name": request.name,
        "rtsp_url": request.rtsp_url,
        "description": request.description
    }
    
    devices_data["devices"].append(new_device)
    devices_data["next_id"] += 1
    
    _save_devices(devices_data)
    
    return {
        "success": True,
        "device_id": new_device["id"],
        "message": f"设备 {request.name} 注册成功"
    }


@router.delete("/unregister/{device_id}")
async def unregister_device(device_id: int) -> dict:
    """
    注销设备。
    
    Args:
        device_id: 设备ID
        
    Returns:
        包含成功状态和消息的字典
    """
    devices_data = _load_devices()
    
    # 查找设备
    device = next((d for d in devices_data["devices"] if d["id"] == device_id), None)
    if not device:
        raise HTTPException(status_code=404, detail=f"设备ID {device_id} 不存在")
    
    # 删除设备
    devices_data["devices"] = [d for d in devices_data["devices"] if d["id"] != device_id]
    _save_devices(devices_data)
    
    return {
        "success": True,
        "message": f"设备 {device['name']} 已注销"
    }


@router.get("/list")
async def list_devices() -> dict:
    """
    获取所有已注册设备列表（不检测在线状态）。
    
    Returns:
        包含所有设备信息的字典
    """
    devices_data = _load_devices()
    
    return {
        "devices": devices_data["devices"],
        "total": len(devices_data["devices"])
    }


@router.get("/info/{device_id}")
async def get_device_info(device_id: int) -> dict:
    """
    获取指定设备的详细信息。
    
    Args:
        device_id: 设备ID
        
    Returns:
        设备详细信息
    """
    devices_data = _load_devices()
    
    device = next((d for d in devices_data["devices"] if d["id"] == device_id), None)
    if not device:
        raise HTTPException(status_code=404, detail=f"设备ID {device_id} 不存在")
    
    # 检测在线状态
    online = _ping_host(device["ip"])
    
    return {
        **device,
        "online": online
    }

