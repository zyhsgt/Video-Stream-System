"""
摄像头基础模型。
"""

from __future__ import annotations

import asyncio
import pickle
from pathlib import Path
from typing import Any, Tuple, TypedDict, Union
from pydantic import BaseModel
from urllib.parse import urlparse
from fastapi import FastAPI, APIRouter

from backend.api.device_management.device_ping import ping_once as _device_ping_once


class CameraData(BaseModel):
    camera_id: str
    camera_ip: str
    camera_name: str
    camera_location: Tuple[float, float]
    accessible: bool
    protocol_in: str
    protocol_out: str

class Camera:
    def __init__(
        self,
        camera_id: str,
        camera_ip: str,
        camera_name: str,
        camera_location: Tuple[float, float],
        accessible: bool,
        protocol_in: str,
        protocol_out: str,
    ) -> None:
        self._camera_id = camera_id
        self._camera_ip = camera_ip
        self._camera_name = camera_name
        self._camera_location = camera_location
        self._accessible = accessible
        self._protocol_in = protocol_in # video_stream: backend (e.g., rtsp_url)
        self._protocol_out = protocol_out # video_stream: frontend(e.g., WebRTC)
        # status_code：HTTP 用 HTTP 状态码；RTSP 用 ffprobe returncode（成功为 0）；未知/失败为 -1
        self._status_code: int = -1
        self._last_ping: dict[str, Any] | None = None

    # getters
    def get_camera_id(self) -> str:
        return self._camera_id

    def get_camera_ip(self) -> str:
        return self._camera_ip

    def get_camera_name(self) -> str:
        return self._camera_name

    def get_camera_location(self) -> Tuple[float, float]:
        return self._camera_location

    def get_accessible(self) -> bool:
        return self._accessible

    def get_protocol_in(self) -> str:
        return self._protocol_in

    def get_protocol_out(self) -> str:
        return self._protocol_out

    def get_status_code(self) -> int:
        return self._status_code

    def get_last_ping(self) -> dict[str, Any] | None:
        return self._last_ping

    def get_meta_data(self):
        return {
            "Camera_name": self.get_camera_name(),
            "Camera_loc": self.get_camera_location(),
            "Camera_ip": self.get_camera_ip(),
            "Camera_id": self.get_camera_id(),
        }


    # setters
    def set_camera_id(self, camera_id: str) -> None:
        self._camera_id = camera_id

    def set_camera_ip(self, camera_ip: str) -> None:
        self._camera_ip = camera_ip

    def set_camera_name(self, camera_name: str) -> None:
        self._camera_name = camera_name

    def set_camera_location(self, camera_location: Tuple[float, float]) -> None:
        self._camera_location = camera_location

    def set_accessible(self, accessible: bool) -> None:
        self._accessible = accessible

    def set_protocol_in(self, protocol_in: str) -> None:
        self._protocol_in = protocol_in

    def set_protocol_out(self, protocol_out: str) -> None:
        self._protocol_out = protocol_out

    def set_status_code(self, status_code: int) -> None:
        self._status_code = status_code

    async def ping_once(self, timeout_s: float = 5.0) -> dict[str, Any]:
        """
        对自身的 `protocol_in` 执行一次连通性检测，并实时更新：
        - accessible：等于本次检测 ok 与否
        - status_code：HTTP 为 status_code；RTSP 为 ffprobe returncode；失败/未知为 -1

        返回值为统一结构的 dict，便于直接打印/序列化。
        """
        url = self.get_protocol_in()
        scheme = (urlparse(url).scheme or "").lower() # 视频流协议 http/rtsp
        if scheme in ("http", "https"):
            protocol = "http"
        elif scheme == "rtsp":
            protocol = "rtsp"
        else:
            # 兜底：按 rtsp 处理（你的 protocol_in 通常是 rtsp_url）
            protocol = "rtsp"

        result = await _device_ping_once(protocol=protocol, url=url, timeout_s=timeout_s)

        # 更新 accessible
        self._accessible = bool(result.ok)

        # 更新 status_code（对齐 device_ping 的 extra 信息）
        status_code = -1
        if protocol == "http":
            try:
                status_code = int(result.extra.get("status_code", -1))
            except Exception:
                status_code = -1
        else:
            try:
                status_code = int(result.extra.get("returncode", 0 if result.ok else 1))
            except Exception:
                status_code = 0 if result.ok else 1

        self._status_code = status_code
        self._last_ping = {
            "ok": result.ok,
            "protocol": result.protocol,
            "url": result.url,
            "checked_at": result.checked_at,
            "elapsed_ms": result.elapsed_ms,
            "detail": result.detail,
            "extra": result.extra,
            "status_code": self._status_code,
        }

        return {
            "Camera_Name": self.get_camera_name(),
            "Camera_Id": self.get_camera_id(),
            "Online": result.ok
        }

        # return dict(self._last_ping) # NOTE: 是否要返回所有的ping的结果, 还是说对于相机来说我只关心它是否可以被ping到是否可以传输视频(只关注result.ok)

    def ping_once_sync(self, timeout_s: float = 5.0) -> dict[str, Any]:
        """
        同步封装，便于脚本/交互式直接调用，内部使用 asyncio.run。
        """
        return asyncio.run(self.ping_once(timeout_s=timeout_s))


    def __repr__(self) -> str:
        return (
            f"Camera(id={self._camera_id}, name={getattr(self, '_camera_name', None)}, "
            f"ip={self._camera_ip}, loc={self._camera_location}, "
            f"accessible={self._accessible}, protocol_in={self._protocol_in}, "
            f"protocol_out={self._protocol_out})"
        )

