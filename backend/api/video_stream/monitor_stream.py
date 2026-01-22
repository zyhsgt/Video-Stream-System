"""
监控流选择与预览相关API
功能：
1. 提供监控设备列表接口
2. 维护视频流地址转换逻辑（RTSP -> FLV/HLS/WebRTC）
3. 获取单个设备的流地址
"""

import json
import os
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/stream", tags=["video_stream"])

# 数据文件路径
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DEVICES_FILE = os.path.join(DATA_DIR, "devices.json")


# ==================== 数据模型 ====================

class Device(BaseModel):
    """监控设备模型"""
    id: str
    name: str
    group: str  # 分组/区域，用于树形结构
    rtsp_url: str  # 原始RTSP地址
    status: str = "online"  # online/offline
    description: Optional[str] = None


class DeviceCreate(BaseModel):
    """创建设备请求模型"""
    id: str
    name: str
    group: str
    rtsp_url: str
    description: Optional[str] = None


class StreamUrlResponse(BaseModel):
    """流地址响应模型"""
    device_id: str
    rtsp_url: str
    flv_url: str
    hls_url: str
    webrtc_url: str


# ==================== 数据持久化 ====================

def ensure_data_dir():
    """确保数据目录存在"""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)


def load_devices() -> list[dict]:
    """从文件加载设备列表"""
    ensure_data_dir()
    if not os.path.exists(DEVICES_FILE):
        # 初始化默认设备数据
        default_devices = [
            {
                "id": "cam001",
                "name": "大门监控",
                "group": "园区入口",
                "rtsp_url": "rtsp://192.168.1.101:554/stream1",
                "status": "online",
                "description": "园区大门主摄像头"
            },
            {
                "id": "cam002",
                "name": "停车场A区",
                "group": "停车场",
                "rtsp_url": "rtsp://192.168.1.102:554/stream1",
                "status": "online",
                "description": "停车场A区监控"
            },
            {
                "id": "cam003",
                "name": "停车场B区",
                "group": "停车场",
                "rtsp_url": "rtsp://192.168.1.103:554/stream1",
                "status": "offline",
                "description": "停车场B区监控"
            },
            {
                "id": "cam004",
                "name": "1号楼大厅",
                "group": "办公楼/1号楼",
                "rtsp_url": "rtsp://192.168.1.104:554/stream1",
                "status": "online",
                "description": "1号楼大厅监控"
            },
            {
                "id": "cam005",
                "name": "2号楼大厅",
                "group": "办公楼/2号楼",
                "rtsp_url": "rtsp://192.168.1.105:554/stream1",
                "status": "online",
                "description": "2号楼大厅监控"
            },
        ]
        save_devices(default_devices)
        return default_devices
    
    with open(DEVICES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_devices(devices: list[dict]):
    """保存设备列表到文件"""
    ensure_data_dir()
    with open(DEVICES_FILE, "w", encoding="utf-8") as f:
        json.dump(devices, f, ensure_ascii=False, indent=2)


# ==================== 流地址转换逻辑 ====================

# 流媒体服务器配置（实际部署时应从配置文件读取）
STREAM_SERVER_HOST = "localhost"
STREAM_SERVER_HTTP_PORT = 8080  # FLV/HLS端口
STREAM_SERVER_WEBRTC_PORT = 8555  # WebRTC端口


def convert_rtsp_to_flv(device_id: str, rtsp_url: str) -> str:
    """
    将RTSP地址转换为FLV播放地址
    假设使用流媒体服务器（如SRS、ZLMediaKit）进行转换
    """
    # 格式: http://{host}:{port}/live/{device_id}.flv
    return f"http://{STREAM_SERVER_HOST}:{STREAM_SERVER_HTTP_PORT}/live/{device_id}.flv"


def convert_rtsp_to_hls(device_id: str, rtsp_url: str) -> str:
    """
    将RTSP地址转换为HLS播放地址
    """
    # 格式: http://{host}:{port}/live/{device_id}/hls.m3u8
    return f"http://{STREAM_SERVER_HOST}:{STREAM_SERVER_HTTP_PORT}/live/{device_id}/hls.m3u8"


def convert_rtsp_to_webrtc(device_id: str, rtsp_url: str) -> str:
    """
    将RTSP地址转换为WebRTC播放地址
    """
    # 格式: webrtc://{host}:{port}/live/{device_id}
    return f"webrtc://{STREAM_SERVER_HOST}:{STREAM_SERVER_WEBRTC_PORT}/live/{device_id}"


def get_all_stream_urls(device_id: str, rtsp_url: str) -> dict:
    """获取设备的所有流地址格式"""
    return {
        "device_id": device_id,
        "rtsp_url": rtsp_url,
        "flv_url": convert_rtsp_to_flv(device_id, rtsp_url),
        "hls_url": convert_rtsp_to_hls(device_id, rtsp_url),
        "webrtc_url": convert_rtsp_to_webrtc(device_id, rtsp_url),
    }


# ==================== API接口 ====================

@router.get("/devices")
async def get_device_list() -> dict:
    """
    获取监控设备列表
    返回所有设备的基本信息，用于前端渲染监控列表
    """
    devices = load_devices()
    return {
        "code": 0,
        "message": "success",
        "data": {
            "total": len(devices),
            "devices": devices
        }
    }


@router.get("/devices/tree")
async def get_device_tree() -> dict:
    """
    获取监控设备树形结构
    按group字段组织成树形结构，用于前端树形渲染
    """
    devices = load_devices()
    
    # 构建树形结构
    tree = {}
    for device in devices:
        group_path = device["group"].split("/")
        current = tree
        
        for i, group_name in enumerate(group_path):
            if group_name not in current:
                current[group_name] = {"_children": {}, "_devices": []}
            
            if i == len(group_path) - 1:
                # 最后一级，添加设备
                current[group_name]["_devices"].append({
                    "id": device["id"],
                    "name": device["name"],
                    "status": device["status"]
                })
            else:
                current = current[group_name]["_children"]
    
    # 转换为前端友好的格式
    def convert_tree(node: dict, name: str = "root") -> dict:
        result = {
            "name": name,
            "children": [],
            "devices": node.get("_devices", [])
        }
        for child_name, child_node in node.get("_children", {}).items():
            result["children"].append(convert_tree(child_node, child_name))
        return result
    
    tree_list = []
    for group_name, group_node in tree.items():
        tree_list.append(convert_tree(group_node, group_name))
    
    return {
        "code": 0,
        "message": "success",
        "data": tree_list
    }


@router.get("/devices/{device_id}")
async def get_device_detail(device_id: str) -> dict:
    """
    获取单个设备详情
    """
    devices = load_devices()
    for device in devices:
        if device["id"] == device_id:
            return {
                "code": 0,
                "message": "success",
                "data": device
            }
    
    raise HTTPException(status_code=404, detail=f"Device {device_id} not found")


@router.get("/url/{device_id}")
async def get_stream_url(device_id: str, format: Optional[str] = None) -> dict:
    """
    获取设备的视频流播放地址
    
    参数:
    - device_id: 设备ID
    - format: 可选，指定返回格式 (flv/hls/webrtc)，不指定则返回所有格式
    
    返回:
    - 转换后的流媒体播放地址
    """
    devices = load_devices()
    device = None
    for d in devices:
        if d["id"] == device_id:
            device = d
            break
    
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")
    
    if device["status"] != "online":
        raise HTTPException(status_code=503, detail=f"Device {device_id} is offline")
    
    rtsp_url = device["rtsp_url"]
    
    if format:
        format = format.lower()
        if format == "flv":
            url = convert_rtsp_to_flv(device_id, rtsp_url)
        elif format == "hls":
            url = convert_rtsp_to_hls(device_id, rtsp_url)
        elif format == "webrtc":
            url = convert_rtsp_to_webrtc(device_id, rtsp_url)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")
        
        return {
            "code": 0,
            "message": "success",
            "data": {
                "device_id": device_id,
                "format": format,
                "url": url
            }
        }
    
    # 返回所有格式
    return {
        "code": 0,
        "message": "success",
        "data": get_all_stream_urls(device_id, rtsp_url)
    }


@router.post("/devices")
async def add_device(device: DeviceCreate) -> dict:
    """
    添加新的监控设备
    """
    devices = load_devices()
    
    # 检查ID是否已存在
    for d in devices:
        if d["id"] == device.id:
            raise HTTPException(status_code=400, detail=f"Device {device.id} already exists")
    
    new_device = {
        "id": device.id,
        "name": device.name,
        "group": device.group,
        "rtsp_url": device.rtsp_url,
        "status": "online",
        "description": device.description
    }
    
    devices.append(new_device)
    save_devices(devices)
    
    return {
        "code": 0,
        "message": "success",
        "data": new_device
    }


@router.delete("/devices/{device_id}")
async def delete_device(device_id: str) -> dict:
    """
    删除监控设备
    """
    devices = load_devices()
    
    for i, device in enumerate(devices):
        if device["id"] == device_id:
            deleted = devices.pop(i)
            save_devices(devices)
            return {
                "code": 0,
                "message": "success",
                "data": deleted
            }
    
    raise HTTPException(status_code=404, detail=f"Device {device_id} not found")


@router.put("/devices/{device_id}/status")
async def update_device_status(device_id: str, status: str) -> dict:
    """
    更新设备状态
    
    参数:
    - status: online 或 offline
    """
    if status not in ["online", "offline"]:
        raise HTTPException(status_code=400, detail="Status must be 'online' or 'offline'")
    
    devices = load_devices()
    
    for device in devices:
        if device["id"] == device_id:
            device["status"] = status
            save_devices(devices)
            return {
                "code": 0,
                "message": "success",
                "data": device
            }
    
    raise HTTPException(status_code=404, detail=f"Device {device_id} not found")
