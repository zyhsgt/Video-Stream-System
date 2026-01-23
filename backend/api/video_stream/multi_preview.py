"""
多设备监控预览相关API
功能：
1. 多路监控视频流同时转发
2. RTSP模拟视频流管理
3. 分屏布局配置
"""

import json
import os
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/multi-preview", tags=["multi_preview"])

# 数据文件路径
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
LAYOUTS_FILE = os.path.join(DATA_DIR, "layouts.json")
SESSIONS_FILE = os.path.join(DATA_DIR, "preview_sessions.json")

# 从monitor_stream导入设备相关函数
from .monitor_stream import load_devices, get_all_stream_urls


# ==================== 数据模型 ====================

class LayoutConfig(BaseModel):
    """分屏布局配置"""
    layout_type: str  # 2x2, 3x3, 4x4, 1+5, 1+7 等
    device_ids: list[str]  # 各窗口对应的设备ID列表


class PreviewSession(BaseModel):
    """预览会话"""
    session_id: str
    layout_type: str
    device_ids: list[str]
    main_device_id: Optional[str] = None  # 主屏设备ID（用于大屏联动）


class SwitchMainRequest(BaseModel):
    """切换主屏请求"""
    device_id: str


# ==================== 布局配置 ====================

# 预定义布局模板
LAYOUT_TEMPLATES = {
    "1x1": {"rows": 1, "cols": 1, "max_devices": 1},
    "2x2": {"rows": 2, "cols": 2, "max_devices": 4},
    "3x3": {"rows": 3, "cols": 3, "max_devices": 9},
    "4x4": {"rows": 4, "cols": 4, "max_devices": 16},
    "1+5": {"rows": 3, "cols": 3, "max_devices": 6, "main_span": [2, 2]},  # 左上大屏+5小屏
    "1+7": {"rows": 4, "cols": 4, "max_devices": 8, "main_span": [2, 2]},  # 左上大屏+7小屏
}


# ==================== 数据持久化 ====================

def ensure_data_dir():
    """确保数据目录存在"""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)


def load_sessions() -> dict:
    """加载预览会话"""
    ensure_data_dir()
    if not os.path.exists(SESSIONS_FILE):
        return {}
    with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_sessions(sessions: dict):
    """保存预览会话"""
    ensure_data_dir()
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(sessions, f, ensure_ascii=False, indent=2)


# ==================== API接口 ====================

@router.get("/layouts")
async def get_layout_templates() -> dict:
    """
    获取可用的分屏布局模板
    """
    return {
        "code": 0,
        "message": "success",
        "data": {
            "layouts": [
                {"type": k, **v} for k, v in LAYOUT_TEMPLATES.items()
            ]
        }
    }


@router.post("/batch-streams")
async def get_batch_streams(config: LayoutConfig) -> dict:
    """
    批量获取多路视频流地址
    用于分屏同时播放多路视频
    
    参数:
    - layout_type: 布局类型 (2x2, 3x3等)
    - device_ids: 设备ID列表
    
    返回:
    - 每个设备的流地址（支持FLV/HLS/WebRTC）
    """
    # 验证布局类型
    if config.layout_type not in LAYOUT_TEMPLATES:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported layout type: {config.layout_type}"
        )
    
    layout = LAYOUT_TEMPLATES[config.layout_type]
    max_devices = layout["max_devices"]
    
    # 验证设备数量
    if len(config.device_ids) > max_devices:
        raise HTTPException(
            status_code=400,
            detail=f"Too many devices for {config.layout_type} layout. Max: {max_devices}"
        )
    
    # 加载设备信息
    devices = load_devices()
    device_map = {d["id"]: d for d in devices}
    
    # 获取每个设备的流地址
    streams = []
    for device_id in config.device_ids:
        if device_id not in device_map:
            streams.append({
                "device_id": device_id,
                "error": "Device not found",
                "status": "error"
            })
            continue
        
        device = device_map[device_id]
        if device["status"] != "online":
            streams.append({
                "device_id": device_id,
                "name": device["name"],
                "error": "Device offline",
                "status": "offline"
            })
            continue
        
        stream_urls = get_all_stream_urls(device_id, device["rtsp_url"])
        streams.append({
            "device_id": device_id,
            "name": device["name"],
            "status": "online",
            "streams": stream_urls
        })
    
    return {
        "code": 0,
        "message": "success",
        "data": {
            "layout": {
                "type": config.layout_type,
                **layout
            },
            "streams": streams
        }
    }


@router.post("/session")
async def create_preview_session(config: LayoutConfig) -> dict:
    """
    创建预览会话
    用于保存当前的分屏配置状态
    """
    import uuid
    
    session_id = str(uuid.uuid4())[:8]
    
    sessions = load_sessions()
    sessions[session_id] = {
        "session_id": session_id,
        "layout_type": config.layout_type,
        "device_ids": config.device_ids,
        "main_device_id": config.device_ids[0] if config.device_ids else None
    }
    save_sessions(sessions)
    
    return {
        "code": 0,
        "message": "success",
        "data": sessions[session_id]
    }


@router.get("/session/{session_id}")
async def get_preview_session(session_id: str) -> dict:
    """
    获取预览会话信息
    """
    sessions = load_sessions()
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "code": 0,
        "message": "success",
        "data": sessions[session_id]
    }


@router.put("/session/{session_id}/main")
async def switch_main_screen(session_id: str, request: SwitchMainRequest) -> dict:
    """
    切换主屏显示的设备
    用于实现点击分屏切换到中间大屏的联动功能
    
    参数:
    - session_id: 会话ID
    - device_id: 要切换到主屏的设备ID
    """
    sessions = load_sessions()
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    # 验证设备是否在当前会话中
    if request.device_id not in session["device_ids"]:
        raise HTTPException(
            status_code=400, 
            detail="Device not in current session"
        )
    
    # 更新主屏设备
    session["main_device_id"] = request.device_id
    save_sessions(sessions)
    
    # 获取主屏设备的流地址
    devices = load_devices()
    device = None
    for d in devices:
        if d["id"] == request.device_id:
            device = d
            break
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    stream_urls = get_all_stream_urls(request.device_id, device["rtsp_url"])
    
    return {
        "code": 0,
        "message": "success",
        "data": {
            "session_id": session_id,
            "main_device_id": request.device_id,
            "main_device_name": device["name"],
            "streams": stream_urls
        }
    }


@router.delete("/session/{session_id}")
async def delete_preview_session(session_id: str) -> dict:
    """
    删除预览会话
    """
    sessions = load_sessions()
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    deleted = sessions.pop(session_id)
    save_sessions(sessions)
    
    return {
        "code": 0,
        "message": "success",
        "data": deleted
    }


@router.get("/rtsp/simulate")
async def get_simulated_rtsp_streams() -> dict:
    """
    获取模拟RTSP视频流列表
    用于测试环境，返回可用的测试流地址
    """
    # 模拟RTSP测试流（实际部署时可替换为真实地址）
    simulated_streams = [
        {
            "id": "test001",
            "name": "测试流1-城市街道",
            "rtsp_url": "rtsp://wowzaec2demo.streamlock.net/vod/mp4:BigBuckBunny_115k.mp4",
            "description": "Wowza公共测试流"
        },
        {
            "id": "test002", 
            "name": "测试流2-自然风景",
            "rtsp_url": "rtsp://wowzaec2demo.streamlock.net/vod/mp4:sample.mp4",
            "description": "Wowza公共测试流"
        },
        {
            "id": "test003",
            "name": "本地测试流",
            "rtsp_url": "rtsp://localhost:8554/live/test",
            "description": "本地RTSP服务器测试流"
        }
    ]
    
    return {
        "code": 0,
        "message": "success",
        "data": {
            "total": len(simulated_streams),
            "streams": simulated_streams,
            "note": "这些是测试用RTSP流，实际部署时请替换为真实监控地址"
        }
    }


@router.post("/rtsp/forward")
async def start_rtsp_forward(device_ids: list[str]) -> dict:
    """
    启动RTSP流转发
    将指定设备的RTSP流转发到流媒体服务器
    
    注意：实际实现需要配合流媒体服务器（如SRS、ZLMediaKit）
    此处返回模拟数据，实际部署时需要调用流媒体服务器API
    """
    devices = load_devices()
    device_map = {d["id"]: d for d in devices}
    
    forward_results = []
    for device_id in device_ids:
        if device_id not in device_map:
            forward_results.append({
                "device_id": device_id,
                "status": "error",
                "message": "Device not found"
            })
            continue
        
        device = device_map[device_id]
        
        # 模拟转发结果（实际需要调用流媒体服务器）
        forward_results.append({
            "device_id": device_id,
            "name": device["name"],
            "status": "forwarding",
            "rtsp_source": device["rtsp_url"],
            "forward_targets": {
                "flv": f"http://localhost:8080/live/{device_id}.flv",
                "hls": f"http://localhost:8080/live/{device_id}/hls.m3u8",
                "webrtc": f"webrtc://localhost:8555/live/{device_id}"
            }
        })
    
    return {
        "code": 0,
        "message": "success",
        "data": {
            "total": len(forward_results),
            "forwards": forward_results,
            "note": "流转发已启动，请确保流媒体服务器正常运行"
        }
    }
