"""
RTSP视频流管理模块

功能：
- 启动/停止FFMPEG推流到RTSP服务器
- 获取当前活跃的视频流列表
- 捕获视频流帧
"""

import base64
import json
import subprocess
import os
from pathlib import Path
from typing import Optional

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


router = APIRouter(prefix="/api/stream", tags=["video_stream"])

# 数据存储路径
DATA_DIR = Path(__file__).parent.parent.parent / "data"
STREAMS_FILE = DATA_DIR / "streams.json"

# 存储活跃的FFMPEG进程
_active_processes: dict[str, subprocess.Popen] = {}


class StartStreamRequest(BaseModel):
    """启动流请求模型"""
    video_path: str
    stream_name: str
    host: str = "127.0.0.1"
    port: int = 8554


class StopStreamRequest(BaseModel):
    """停止流请求模型"""
    stream_name: str


class CaptureFrameRequest(BaseModel):
    """捕获帧请求模型"""
    rtsp_url: str


def _ensure_data_dir() -> None:
    """确保数据目录存在"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_streams() -> dict:
    """加载流配置"""
    _ensure_data_dir()
    if STREAMS_FILE.exists():
        with open(STREAMS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"streams": []}


def _save_streams(data: dict) -> None:
    """保存流配置"""
    _ensure_data_dir()
    with open(STREAMS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@router.post("/start")
async def start_stream(request: StartStreamRequest) -> dict:
    """
    启动视频流推送。
    
    使用FFMPEG将本地视频推送到RTSP服务器。
    
    Args:
        request: 包含video_path, stream_name, host, port的请求
        
    Returns:
        包含成功状态和RTSP URL的字典
    """
    # 检查视频文件是否存在
    if not os.path.exists(request.video_path):
        raise HTTPException(status_code=400, detail=f"视频文件不存在: {request.video_path}")
    
    # 检查流是否已存在
    if request.stream_name in _active_processes:
        raise HTTPException(status_code=400, detail=f"流 {request.stream_name} 已在运行")
    
    # 构建RTSP URL
    rtsp_url = f"rtsp://{request.host}:{request.port}/live/{request.stream_name}"
    
    # 构建FFMPEG命令
    # -re: 以原始帧率读取
    # -stream_loop -1: 循环播放
    # -c copy: 复制编码（不重新编码）
    # -f rtsp: 输出格式为RTSP
    ffmpeg_cmd = [
        "ffmpeg",
        "-re",
        "-stream_loop", "-1",
        "-i", request.video_path,
        "-c", "copy",
        "-f", "rtsp",
        rtsp_url
    ]
    
    try:
        # 启动FFMPEG进程
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        # 存储进程引用
        _active_processes[request.stream_name] = process
        
        # 更新持久化数据
        streams_data = _load_streams()
        stream_info = {
            "name": request.stream_name,
            "video_path": request.video_path,
            "rtsp_url": rtsp_url,
            "host": request.host,
            "port": request.port
        }
        
        # 检查是否已存在，更新或添加
        existing = [s for s in streams_data["streams"] if s["name"] == request.stream_name]
        if existing:
            existing[0].update(stream_info)
        else:
            streams_data["streams"].append(stream_info)
        
        _save_streams(streams_data)
        
        return {
            "success": True,
            "rtsp_url": rtsp_url,
            "message": f"视频流 {request.stream_name} 已启动"
        }
        
    except FileNotFoundError:
        raise HTTPException(
            status_code=500, 
            detail="FFMPEG未安装或不在系统PATH中"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动流失败: {str(e)}")


@router.post("/stop")
async def stop_stream(request: StopStreamRequest) -> dict:
    """
    停止视频流推送。
    
    终止对应的FFMPEG进程。
    
    Args:
        request: 包含stream_name的请求
        
    Returns:
        包含成功状态和消息的字典
    """
    stream_name = request.stream_name
    
    if stream_name not in _active_processes:
        raise HTTPException(status_code=404, detail=f"流 {stream_name} 未在运行")
    
    try:
        # 终止进程
        process = _active_processes[stream_name]
        process.terminate()
        process.wait(timeout=5)
        
        # 移除进程引用
        del _active_processes[stream_name]
        
        # 更新持久化数据
        streams_data = _load_streams()
        streams_data["streams"] = [
            s for s in streams_data["streams"] if s["name"] != stream_name
        ]
        _save_streams(streams_data)
        
        return {
            "success": True,
            "message": f"视频流 {stream_name} 已停止"
        }
        
    except subprocess.TimeoutExpired:
        # 强制杀死进程
        _active_processes[stream_name].kill()
        del _active_processes[stream_name]
        return {
            "success": True,
            "message": f"视频流 {stream_name} 已强制停止"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"停止流失败: {str(e)}")


@router.get("/list")
async def list_streams() -> dict:
    """
    获取当前活跃的视频流列表。
    
    Returns:
        包含所有活跃流信息的字典
    """
    active_streams = []
    
    for stream_name, process in list(_active_processes.items()):
        # 检查进程是否仍在运行
        if process.poll() is None:
            streams_data = _load_streams()
            stream_info = next(
                (s for s in streams_data["streams"] if s["name"] == stream_name),
                {"name": stream_name, "rtsp_url": "unknown"}
            )
            active_streams.append({
                "name": stream_name,
                "rtsp_url": stream_info.get("rtsp_url", "unknown"),
                "video_path": stream_info.get("video_path", "unknown"),
                "status": "running"
            })
        else:
            # 进程已结束，清理
            del _active_processes[stream_name]
    
    return {"streams": active_streams, "count": len(active_streams)}


@router.post("/capture")
async def capture_frame(request: CaptureFrameRequest) -> dict:
    """
    从RTSP流捕获一帧图像。
    
    使用OpenCV捕获视频流的一帧并返回base64编码的图像。
    
    Args:
        request: 包含rtsp_url的请求
        
    Returns:
        包含成功状态和base64编码图像的字典
    """
    if not CV2_AVAILABLE:
        raise HTTPException(
            status_code=503, 
            detail="OpenCV未安装，无法使用帧捕获功能。请安装: pip install opencv-python"
        )
    
    rtsp_url = request.rtsp_url
    
    try:
        # 使用OpenCV捕获视频流
        cap = cv2.VideoCapture(rtsp_url)
        
        if not cap.isOpened():
            raise HTTPException(status_code=400, detail=f"无法连接到视频流: {rtsp_url}")
        
        # 读取一帧
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            raise HTTPException(status_code=500, detail="无法读取视频帧")
        
        # 将帧编码为JPEG
        _, buffer = cv2.imencode('.jpg', frame)
        
        # 转换为base64
        frame_base64 = base64.b64encode(buffer).decode('utf-8')
        
        return {
            "success": True,
            "frame": frame_base64,
            "width": frame.shape[1],
            "height": frame.shape[0]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"捕获帧失败: {str(e)}")


@router.get("/test")
async def test_stream_api() -> dict:
    """测试接口，用于验证API是否可用。"""
    return {"message": "Video Stream API is working"}

