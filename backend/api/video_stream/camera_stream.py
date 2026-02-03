"""
基于 CameraData/Camera 数据结构的监控流选择与预览相关 API。

说明：
- CameraData.protocol_in：RTSP URL
- CameraData.protocol_out：由 RTSP 转换得到的播放 URL（FLV/HLS/WebRTC 之一）

该模块在功能上等价于 monitor_stream.py，但对外数据结构对齐 backend/api/Camera.py。
"""

import json
import os
from typing import Optional, Literal, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.api.Camera import CameraData
from backend.api.Buffer import device_ip

# from backend.api.device_management.camera_operation import _registry

router = APIRouter(prefix="/api/stream", tags=["video_stream"])

# 数据文件路径（沿用 monitor_stream.py 的持久化文件）
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DEVICES_FILE = os.path.join(DATA_DIR, "devices.json")


# ==================== 请求/响应模型（围绕 CameraData） ====================

class CameraCreate(BaseModel):
    camera_id: str
    camera_ip: str
    camera_name: str
    camera_location: tuple[float, float]
    group: str
    protocol_in: str
    description: Optional[str] = None


class StreamUrlResponse(BaseModel):
    camera_id: str
    protocol_in: str
    flv_url: str
    hls_url: str
    webrtc_url: str


# ==================== 数据持久化（兼容旧 devices.json） ====================

def ensure_data_dir() -> None:
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)


def _legacy_device_to_camera_data(device: dict[str, Any]) -> CameraData:
    # monitor_stream.py: {id,name,group,rtsp_url,status,description}
    cam_id = device.get("id")
    rtsp = device.get("rtsp_url")
    name = device.get("name")

    # 尝试从 rtsp host 推断 ip（不强依赖）
    camera_ip = ""
    try:
        if isinstance(rtsp, str) and rtsp.startswith("rtsp://"):
            rest = rtsp[len("rtsp://") :]
            hostport = rest.split("/", 1)[0]
            camera_ip = hostport.split(":", 1)[0]
    except Exception:
        camera_ip = ""

    return CameraData(
        camera_id=str(cam_id) if cam_id is not None else "",
        camera_ip=camera_ip,
        camera_name=str(name) if name is not None else "",
        camera_location=(0.0, 0.0),
        accessible=(device.get("status") == "online"),
        protocol_in=rtsp,
        protocol_out=None,
        video_path="",
    )


def _camera_create_to_legacy_device(cam: CameraCreate) -> dict[str, Any]:
    return {
        "id": cam.camera_id,
        "name": cam.camera_name,
        "group": cam.group,
        "rtsp_url": cam.protocol_in,
        "status": "online",
        "description": cam.description,
    }


def load_devices() -> list[dict[str, Any]]:
    ensure_data_dir()
    if not os.path.exists(DEVICES_FILE):
        # 初始化默认数据（与 monitor_stream.py 对齐）
        default_devices: list[dict[str, Any]] = [
            {
                "id": "cam001",
                "name": "大门监控",
                "group": "园区入口",
                "rtsp_url": "rtsp://192.168.1.101:554/stream1",
                "status": "online",
                "description": "园区大门主摄像头",
            },
            {
                "id": "cam002",
                "name": "停车场A区",
                "group": "停车场",
                "rtsp_url": "rtsp://192.168.1.102:554/stream1",
                "status": "online",
                "description": "停车场A区监控",
            },
            {
                "id": "cam003",
                "name": "停车场B区",
                "group": "停车场",
                "rtsp_url": "rtsp://192.168.1.103:554/stream1",
                "status": "offline",
                "description": "停车场B区监控",
            },
            {
                "id": "cam004",
                "name": "1号楼大厅",
                "group": "办公楼/1号楼",
                "rtsp_url": "rtsp://192.168.1.104:554/stream1",
                "status": "online",
                "description": "1号楼大厅监控",
            },
            {
                "id": "cam005",
                "name": "2号楼大厅",
                "group": "办公楼/2号楼",
                "rtsp_url": "rtsp://192.168.1.105:554/stream1",
                "status": "online",
                "description": "2号楼大厅监控",
            },
        ]
        save_devices(default_devices)
        return default_devices

    with open(DEVICES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_devices(devices: list[dict[str, Any]]) -> None:
    ensure_data_dir()
    with open(DEVICES_FILE, "w", encoding="utf-8") as f:
        json.dump(devices, f, ensure_ascii=False, indent=2)


# ==================== 流地址转换逻辑 ====================

STREAM_SERVER_HOST = device_ip
STREAM_SERVER_HTTP_PORT = 8080
STREAM_SERVER_WEBRTC_PORT = 8889


def convert_rtsp_to_flv(camera_id: str, rtsp_url: str) -> str:
    return f"http://{STREAM_SERVER_HOST}:{STREAM_SERVER_HTTP_PORT}/live/{camera_id}.flv"


def convert_rtsp_to_hls(camera_id: str, rtsp_url: str) -> str:
    return f"http://{STREAM_SERVER_HOST}:{STREAM_SERVER_HTTP_PORT}/live/{camera_id}/hls.m3u8"


def convert_rtsp_to_webrtc(camera_ip:str, camera_id: str, rtsp_url: str) -> str:
    return f"http://{camera_ip}:{STREAM_SERVER_WEBRTC_PORT}/live/{camera_id}/whep"


def get_all_stream_urls(camera_id: str, rtsp_url: str) -> dict[str, str]:
    return {
        "camera_id": camera_id,
        "protocol_in": rtsp_url,
        "flv_url": convert_rtsp_to_flv(camera_id, rtsp_url),
        "hls_url": convert_rtsp_to_hls(camera_id, rtsp_url),
        "webrtc_url": convert_rtsp_to_webrtc(camera_id, rtsp_url),
    }


# ==================== API ====================

@router.get("/cameras")
async def get_camera_list() -> dict:
    devices = load_devices()
    cameras = []
    for d in devices:
        cam = _legacy_device_to_camera_data(d)
        # 按约定：protocol_out 是“转换后的URL”，列表场景不给定具体格式时置空
        cam.protocol_out = None
        cameras.append(cam.model_dump())

    return {
        "code": 0,
        "message": "success",
        "data": {"total": len(cameras), "cameras": cameras},
    }


@router.get("/cameras/tree")
async def get_camera_tree() -> dict:
    devices = load_devices()

    tree: dict[str, Any] = {}
    for device in devices:
        group_path = str(device.get("group", "")).split("/") if device.get("group") else [""]
        current = tree
        for i, group_name in enumerate(group_path):
            if group_name not in current:
                current[group_name] = {"_children": {}, "_devices": []}
            if i == len(group_path) - 1:
                current[group_name]["_devices"].append(
                    {
                        "camera_id": device.get("id"),
                        "camera_name": device.get("name"),
                        "accessible": (device.get("status") == "online"),
                    }
                )
            else:
                current = current[group_name]["_children"]

    def convert_tree(node: dict, name: str = "root") -> dict:
        result = {"name": name, "children": [], "cameras": node.get("_devices", [])}
        for child_name, child_node in node.get("_children", {}).items():
            result["children"].append(convert_tree(child_node, child_name))
        return result

    tree_list = [convert_tree(group_node, group_name) for group_name, group_node in tree.items()]

    return {"code": 0, "message": "success", "data": tree_list}


@router.get("/cameras/{camera_id}")
async def get_camera_detail(camera_id: str) -> dict:
    devices = load_devices()
    for device in devices:
        if device.get("id") == camera_id:
            cam = _legacy_device_to_camera_data(device)
            # 详情里默认也不强行指定 protocol_out
            cam.protocol_out = None
            return {"code": 0, "message": "success", "data": cam.model_dump()}

    raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")


@router.get("/cameras/{stream_name}/url")
async def get_camera_stream_url(
    stream_name: str,
    format: Optional[Literal["flv", "hls", "webrtc"]] = None,
) -> dict:
    '''
    这里给人的感觉更像是创建前端的url, 但是数据结构(CameraData)或者Camera类中有protocol_out指代前端的url, 这个函数可能不会使用
    因为RTSP URL生成是按照 {camera_name}_{camera_id}来命名的, 所以这里接收一个参数：stream_name，会把其解析为camera_id和camera_name
    '''
    # devices = load_devices() # 统一从_registry中读取内存中的摄像头参数
    # device = next((d for d in devices if d.get("id") == camera_id), None)
    camera_id = stream_name.split("_")[-1] # camera_name中可以包含"_"但是camera_id中不能包含"_"
    devices = _registry
    device = next((d for d in devices if d.camera_id == camera_id), None)
    if not device:
        raise HTTPException(status_code=404, detail=f"Camera {stream_name} not found")

    if device.get("status") != "online":
        raise HTTPException(status_code=503, detail=f"Camera {stream_name} is offline")

    rtsp_url = device.get("rtsp_url")
    if not rtsp_url:
        raise HTTPException(status_code=500, detail=f"Camera {stream_name} rtsp_url missing")

    if format:
        if format == "flv":
            out_url = convert_rtsp_to_flv(stream_name, rtsp_url)
        elif format == "hls":
            out_url = convert_rtsp_to_hls(stream_name, rtsp_url)
        elif format == "webrtc":
            out_url = convert_rtsp_to_webrtc(stream_name, rtsp_url)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

        cam = _legacy_device_to_camera_data(device)
        cam.protocol_out = out_url

        return {
            "code": 0,
            "message": "success",
            "data": {
                "camera": cam.model_dump(),
                "format": format,
                "url": out_url,
            },
        }

    # 不指定 format：返回全部格式，同时返回 camera（protocol_out 为空）
    cam = _legacy_device_to_camera_data(device)
    cam.protocol_out = None

    return {
        "code": 0,
        "message": "success",
        "data": {
            "camera": cam.model_dump(),
            "urls": get_all_stream_urls(stream_name, rtsp_url),
        },
    }


@router.post("/cameras")
async def add_camera(camera: CameraCreate) -> dict:
    devices = load_devices()
    if any(d.get("id") == camera.camera_id for d in devices):
        raise HTTPException(status_code=400, detail=f"Camera {camera.camera_id} already exists")

    new_device = _camera_create_to_legacy_device(camera)
    devices.append(new_device)
    save_devices(devices)

    cam = _legacy_device_to_camera_data(new_device)
    cam.protocol_out = None

    return {"code": 0, "message": "success", "data": cam.model_dump()}


@router.delete("/cameras/{camera_id}")
async def delete_camera(camera_id: str) -> dict:
    devices = load_devices()
    for i, device in enumerate(devices):
        if device.get("id") == camera_id:
            deleted = devices.pop(i)
            save_devices(devices)
            cam = _legacy_device_to_camera_data(deleted)
            cam.protocol_out = None
            return {"code": 0, "message": "success", "data": cam.model_dump()}

    raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")


@router.put("/cameras/{camera_id}/status")
async def update_camera_status(camera_id: str, status: Literal["online", "offline"]) -> dict:
    devices = load_devices()
    for device in devices:
        if device.get("id") == camera_id:
            device["status"] = status
            save_devices(devices)
            cam = _legacy_device_to_camera_data(device)
            cam.protocol_out = None
            return {"code": 0, "message": "success", "data": cam.model_dump()}

    raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")
