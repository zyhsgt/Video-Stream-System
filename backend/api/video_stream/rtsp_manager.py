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
from typing import Optional, Union, List

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
import socket
from backend.api.Buffer import device_ip


router = APIRouter(prefix="/api/stream", tags=["video_stream"])

# 数据存储路径
DATA_DIR = Path(__file__).parent.parent.parent / "data"
STREAMS_FILE = DATA_DIR / "streams.json"

# 存储活跃的FFMPEG进程
# _active_processes: dict[str, subprocess.Popen] = {} # rtsp url: ffmpeg进程
from backend.api.Buffer import _active_processes


class StartStreamRequest(BaseModel):
    """启动流请求模型"""
    camera_id: Union[str, List[str]]
    camera_name: Union[str, List[str]]
    video_path: Union[str, List[str]]
    host: Optional[Union[str, List[str]]] = "127.0.0.1"
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

async def is_port_open(host = "127.0.0.1", port = 8554, timeout=1):
    '''
    检测rtsp推流端口是否可用, 这里只是简单检测一下, 一般只有mediamtx会在8554端口推流, 这里如果被其他程序占用端口则没办法检测mediamtx是否开启推流
    其他方法进行检测会比较复杂并且可能会导致不同电脑频繁更换配置, 因此需要十分确定这个8554端口和mediamtx是深度绑定的(在mediamtx.yml配置文件中设置rtspAddress端口为8554, 一般是默认的)
    '''
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except Exception:
            return False

@router.post("/start")
async def start_stream(request: StartStreamRequest) -> dict: # ATTN: 通过video_path获取RTSP URL
    """
    启动视频流推送。
    
    使用FFMPEG将本地视频推送到RTSP服务器。
    
    Args:
        request: 包含video_path, stream_name, host, port的请求
        
    Returns:
        包含成功状态和RTSP URL的字典
    """
    # 兼容 video_path 为 str 或 list[str]
    if isinstance(request.video_path, str):
        video_paths = [request.video_path]
    else:
        video_paths = list(request.video_path)

    # 基本校验
    if not video_paths:
        raise HTTPException(status_code=400, detail="video_path 不能为空")

    invalid_paths = [p for p in video_paths if not isinstance(p, str) or not p.strip()]
    if invalid_paths:
        raise HTTPException(status_code=400, detail=f"video_path 中存在非法路径: {invalid_paths}")

    # 检查视频文件是否存在
    missing_paths = [p for p in video_paths if not os.path.exists(p)]
    if missing_paths:
        raise HTTPException(status_code=400, detail=f"视频文件不存在: {missing_paths}")
    

    # 兼容 stream_name 为 str 或 list[str]，并与 video_path 一一对应
    if isinstance(request.camera_id, str):
        camera_ids = [request.camera_id]
    else:
        camera_ids = list(request.camera_id)

    if isinstance(request.camera_name, str):
        camera_names = [request.camera_name]
    else:
        camera_names = list(request.camera_name)

    if isinstance(request.host, str):
        camera_hosts = [request.host]
        if camera_hosts[0] == "127.0.0.1":
            camera_hosts = ["127.0.0.1"]*len(camera_ids)
    else:
        camera_names = list(request.camera_name)

    if not (len(camera_ids) == len(video_paths) == len(camera_names) == len(camera_hosts)):
        raise HTTPException(
            status_code=400,
            detail=f"video_path、camera_ids、camera_names、camera_hosts 数量不一致: {len(video_paths)} vs {len(camera_ids)} vs {len(camera_names)} vs {len(camera_hosts)}"
        )

    # 如果一次请求启动多个流，返回每个流的 rtsp_url
    # 单个流保持原返回结构，尽量兼容旧调用方
    stream_results: list[dict] = []

    for video_path, camera_id, camera_name, camera_host in zip(video_paths, camera_ids, camera_names, camera_hosts):
        stream_name = f"{camera_id}"
        if stream_name in _active_processes:
            raise HTTPException(status_code=400, detail=f"流 {stream_name} 已在运行")

        MEDIAMTX_OPEN = await is_port_open()
        if not MEDIAMTX_OPEN:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="mediamtx没有打开, 并且请确保8554端口是和meidia.yml配置文件中的rtspAddress相匹配"
            )
        rtsp_url = f"rtsp://{camera_host}:{request.port}/live/{stream_name}"
        print(rtsp_url)
        print(video_path)
        ffmpeg_cmd = [
            "ffmpeg",
            "-re",
            # "-stream_loop", "-1",
            "-i", video_path,
            "-c", "copy",
            "-f", "rtsp",
            rtsp_url,
            # "-rtsp_transport", "tcp",
        ]

        try:
            process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.DEVNULL, # ATTN: 使用subprocess.PIPE会导致FFmpeg将输出的内容存放到python缓冲区, 并且这里没有写读取(消耗)缓冲区信息的代码会导致缓冲区堵塞, 将推流停止
                stderr=subprocess.DEVNULL, # ATTN: 同上, 使用subprocess.DEVNULL不会将输出内容放到缓冲区
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
        except FileNotFoundError:
            raise HTTPException(
                status_code=500,
                detail="FFMPEG未安装或不在系统PATH中"
            )

        _active_processes[stream_name] = process

        streams_data = _load_streams()
        stream_info = {
            "name": stream_name,
            "video_path": video_path,
            "rtsp_url": rtsp_url,
            "host": request.host,
            "port": request.port
        }

        existing = [s for s in streams_data["streams"] if s["name"] == stream_name]
        if existing:
            existing[0].update(stream_info)
        else:
            streams_data["streams"].append(stream_info)

        _save_streams(streams_data)

        stream_results.append({
            "stream_name": stream_name,
            "rtsp_url": rtsp_url
        })

    if len(stream_results) == 1:
        return {
            "success": True,
            "rtsp_url": stream_results[0]["rtsp_url"],
            "message": f"视频流 {stream_results[0]['stream_name']} 已启动"
        }

    return {
        "success": True,
        "streams": stream_results,
        "message": f"已启动 {len(stream_results)} 路视频流"
    }


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
        _active_processes[stream_name].kill()
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

