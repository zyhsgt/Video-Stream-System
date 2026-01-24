"""
使用 ffprobe 检测 RTSP 流是否可访问。

命令参考：
ffprobe -v error -show_entries format=format_name -of default=noprint_wrappers=1 -i <rtsp_url> -stimeout 2000000
"""

from __future__ import annotations

import asyncio
import shutil
import time
from typing import Any, Dict


async def probe_rtsp_with_ffprobe(url: str, timeout_ms: int = 2_000_000) -> Dict[str, Any]:
    """
    调用 ffprobe 检测 RTSP：
    - timeout_ms 会同时用于 ffprobe 的 -stimeout（微秒）参数，并用 asyncio.wait_for 再兜底一次。
    返回字段包含 returncode、stdout、stderr、elapsed_ms 便于上层生成 PingResult。
    """
    if not shutil.which("ffprobe"):
        raise RuntimeError("未找到 ffprobe，请确认已安装 FFmpeg 并在 PATH 中可用")

    stimeout = max(timeout_ms, 1)
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=format_name",
        "-of",
        "default=noprint_wrappers=1",
        "-i",
        url,
        "-timeout",
        str(stimeout),
    ]

    start = time.perf_counter()
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=stimeout / 1000.0 + 1  # 给 stimeout 微秒参数再加 1 秒缓冲
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return {
        "returncode": proc.returncode,
        "stdout": (stdout or b"").decode(errors="ignore"),
        "stderr": (stderr or b"").decode(errors="ignore"),
        "elapsed_ms": elapsed_ms,
        "cmd": cmd,
    }

