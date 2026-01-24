"""
简单的设备连通性测试脚本。

示例：使用 ffprobe 逻辑检测本地 RTSP 流是否可用。
"""

import asyncio
from typing import NoReturn

from backend.api.device_management.device_ping import ping_once


RTSP_URL = "rtsp://127.0.0.1:8554/live/camera1"


async def main() -> None:
    while True:
        result = await ping_once(protocol="rtsp", url=RTSP_URL, timeout_s=5.0)
        print(
            {
                "ok": result.ok,
                "protocol": result.protocol,
                "url": result.url,
                "checked_at": result.checked_at,
                "elapsed_ms": result.elapsed_ms,
                "detail": result.detail,
                "extra": result.extra,
            }
        )


def run() -> NoReturn:
    asyncio.run(main())


if __name__ == "__main__":
    run()

