"""
设备连通性/流可用性检测（HTTP / RTSP）。

功能：
1) 一次性检测：立即检查某个 URL 是否可访问（HTTP）/ 是否能打开并读到帧（RTSP）。
2) 定期检测：注册若干目标，后台按固定间隔循环检测，并记录最近一次结果。
"""

from __future__ import annotations

import asyncio
import pickle
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field
from backend.api.device_management.rtsp_ffprobe import probe_rtsp_with_ffprobe
# from backend.api.Camera import _DB_PATH as _Camera_DB_PAHT

client = httpx.AsyncClient(timeout=0.5)


ProtocolType = Literal["http", "rtsp"]


# ping function
async def _ping_http(url: str, timeout_s: float) -> PingResult:
    start = time.perf_counter()
    try:
        timeout = httpx.Timeout(timeout_s) # HTTP 专用超时对象
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            # 优先 HEAD，失败再 GET（某些设备/服务不支持 HEAD）
            try:
                resp = await client.head(url)
            except Exception:
                resp = await client.get(url)

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        ok = 200 <= resp.status_code < 400 # HTTP状态码, 在200-400之前表示正常
        return PingResult(
            ok=ok,
            protocol="http",
            url=url,
            elapsed_ms=elapsed_ms,
            detail=f"status_code={resp.status_code}",
            extra={"status_code": resp.status_code},
        )
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return PingResult(
            ok=False,
            protocol="http",
            url=url,
            elapsed_ms=elapsed_ms,
            detail=f"{type(e).__name__}: {e}",
        )


async def _ping_rtsp(url: str, timeout_s: float) -> PingResult:
    start = time.perf_counter()
    timeout_ms = max(int(timeout_s * 1000), 1)
    try:
        info = await probe_rtsp_with_ffprobe(url, timeout_ms=timeout_ms)
        elapsed_ms = info.get("elapsed_ms", int((time.perf_counter() - start) * 1000))
        ok = info.get("returncode", 1) == 0
        detail = info.get("detail") or f"ffprobe returncode={info.get('returncode')}"
        return PingResult(
            ok=ok,
            protocol="rtsp",
            url=url,
            elapsed_ms=elapsed_ms,
            detail=detail,
            extra=info,
        )
    except asyncio.TimeoutError:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return PingResult(
            ok=False,
            protocol="rtsp",
            url=url,
            elapsed_ms=elapsed_ms,
            detail="TimeoutError: ffprobe wait timeout",
        )
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return PingResult(
            ok=False,
            protocol="rtsp",
            url=url,
            elapsed_ms=elapsed_ms,
            detail=f"{type(e).__name__}: {e}",
        )

async def _is_rtsp_stream_ready(stream_name: str):
    # MediaMTX 默认 API 端口是 9997
    api_url = f"http://127.0.0.1:9997/v3/paths/get/{stream_name}"
    # if stream_name.find("Camera4_748726") != -1:
    #     print(stream_name)
    # async with httpx.AsyncClient() as client:
    try:
        resp = await client.get(api_url)
        if resp.status_code == 200:
            # ready 为 true 表示推流正在运行且可以被拉取
            return resp.json().get("ready", False)
    except Exception:
        return False
    return False

async def ping_once(protocol: ProtocolType, url: str, timeout_s: float) -> PingResult:
    if protocol == "http":
        return await _ping_http(url, timeout_s)
    if protocol == "rtsp":
        # return await _ping_rtsp(url, timeout_s)
        stream_name = url.split(":")[-1][5:]
        stream_is_open = await _is_rtsp_stream_ready(stream_name)
        return PingResult(
            ok=stream_is_open,
            protocol="rtsp",
            url=url,
            elapsed_ms=0.,
            detail="None",
            extra="None",
        )
    raise ValueError(f"unsupported protocol: {protocol}")

@dataclass
class PingResult:
    ok: bool
    protocol: ProtocolType
    url: str
    checked_at: float = field(default_factory=lambda: time.time())
    elapsed_ms: int = 0
    detail: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


class PingRequest(BaseModel):
    protocol: ProtocolType = Field(..., description="http 或 rtsp")
    url: str = Field(..., description="目标 URL，例如 http(s)://... 或 rtsp://...")
    timeout_s: float = Field(5.0, ge=0.5, le=60.0, description="超时时间（秒）")


class RegisterRequest(BaseModel):
    id: str = Field(..., description="自定义目标ID（用于查询/删除）")
    protocol: ProtocolType = Field(..., description="http 或 rtsp")
    url: str = Field(..., description="目标 URL")
    timeout_s: float = Field(5.0, ge=0.5, le=60.0, description="单次检测超时（秒）")

class PingManager:
    """
    轻量级后台定时检测管理器（纯内存）。
    - 适合开发/单进程；生产多进程/多实例需要改成共享存储（DB/Redis）。
    """

    def __init__(self, interval_s: float = 10.0) -> None:
        self._interval_s = interval_s
        self._targets: Dict[str, RegisterRequest] = self.get_all_camera()
        self._last_results: Dict[str, PingResult] = {}
        self._task: Optional[asyncio.Task[None]] = None
        self._stop_event = asyncio.Event()
        self._lock = asyncio.Lock()
        self._camera_db = _Camera_DB_PAHT # NOTE: 暂时使用本地 pickle 文件

    @property
    def interval_s(self) -> float:
        return self._interval_s

    def is_running(self) -> bool:
        task = self._task
        return task is not None and not self._task.done()

    async def start(self) -> None:
        if self.is_running():
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop(), name="device_ping_loop")

    async def stop(self) -> None:
        if not self._task:
            return
        self._stop_event.set()
        try:
            await self._task
        finally:
            self._task = None

    async def get_all_camera(self):
        async with self._lock:
            with open(self._camera_db, 'rb') as f:
                all_camera =pickle.load(f) # list[Camera]
                f.close()

            interval_s = self._interval_s
            for camera in all_camera:
                req = RegisterRequest(
                    id = camera.get_camera_id(),
                    protocol = "rtsp",
                    url = camera.get_protocal_in(),
                    timeout_s = interval_s
                )
                self.register(req)


    async def register(self, req: RegisterRequest) -> None: # 注册一些常用固定设备, 但是目前没有将其保存到数据库/文件
        async with self._lock:
            self._targets[req.id] = req

    async def unregister(self, target_id: str) -> None: # 为什么要unregist?
        async with self._lock:
            self._targets.pop(target_id, None)
            self._last_results.pop(target_id, None)

    async def get_ping_result(self, target_id):
        async with self._lock:
            return self._last_results[target_id]

    async def list_targets(self) -> Dict[str, RegisterRequest]:
        async with self._lock:
            return dict(self._targets)

    async def get_status(self) -> Dict[str, PingResult]:
        async with self._lock:
            return dict(self._last_results)

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            targets = await self.list_targets() # 所有的请求(protocol、url、time_out)
            for target_id, req in targets.items():
                try:
                    result = await ping_once(req.protocol, req.url, req.timeout_s) # ATTN: _run_loop是一个线程, 所有url一个一个ping
                except Exception as e:  # pragma: no cover
                    result = PingResult(
                        ok=False,
                        protocol=req.protocol,
                        url=req.url,
                        detail=f"exception: {type(e).__name__}: {e}",
                    )
                async with self._lock:
                    self._last_results[target_id] = result
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_s)
            except asyncio.TimeoutError:
                pass

_manager: Optional[PingManager] = None
router = APIRouter(prefix="/api/device", tags=["device_management"])

@router.get("/ping/running")
async def ping_running() -> dict:
    global _manager

    if _manager is None:
        _manager = PingManager(interval_s=10.0)
    return {"running": _manager.is_running(), "interval_s": _manager.interval_s}


@router.post("/ping/check")
async def ping_check(req: PingRequest) -> dict:
    result = await ping_once(req.protocol, req.url, req.timeout_s)
    return {
        "ok": result.ok,
        "protocol": result.protocol,
        "url": result.url,
        "checked_at": result.checked_at,
        "elapsed_ms": result.elapsed_ms,
        "detail": result.detail,
        "extra": result.extra,
    }


# 需要提前注册ping请求吗?
@router.post("/ping/register")
async def ping_register(req: RegisterRequest) -> dict:
    await _manager.register(req)
    return {"ok": True, "id": req.id}


@router.delete("/ping/unregister/{target_id}")
async def ping_unregister(target_id: str) -> dict:
    await _manager.unregister(target_id)
    return {"ok": True, "id": target_id}


@router.get("/ping/status")
async def ping_status() -> dict:
    status = await _manager.get_status()
    return {
        "ok": True,
        "status": {
            target_id: {
                "ok": r.ok,
                "protocol": r.protocol,
                "url": r.url,
                "checked_at": r.checked_at,
                "elapsed_ms": r.elapsed_ms,
                "detail": r.detail,
                "extra": r.extra,
            }
            for target_id, r in status.items()
        },
    }

@router.post("/ping/start")
async def ping_start() -> dict:
    await _manager.start()
    return {"ok": True}


@router.post("/ping/stop")
async def ping_stop() -> dict:
    await _manager.stop()
    return {"ok": True}


def get_ping_manager() -> PingManager:
    return _manager
