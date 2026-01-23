"""
FastAPI 应用入口。

在这里创建 FastAPI 实例，并挂载各个子路由。

启动命令（在项目根目录 `Video-Stream-System` 下执行）：

    uvicorn backend.main:app --reload

"""

from fastapi import FastAPI

# 设备管理模块
from backend.api.device_management.hello_world import router as hello_world_router
from backend.api.device_management.device_state import router as device_state_router
from backend.api.device_management.device_monitor import router as device_monitor_router

# 视频流模块
from backend.api.video_stream.monitor_stream import router as monitor_stream_router
from backend.api.video_stream.multi_preview import router as multi_preview_router
from backend.api.video_stream.rtsp_manager import router as rtsp_manager_router


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。"""
    app = FastAPI(
        title="视频轮播系统后端",
        version="1.0.0",
    )

    # 注册路由 - 设备管理
    app.include_router(hello_world_router)
    app.include_router(device_state_router)
    app.include_router(device_monitor_router)

    # 注册路由 - 视频流
    app.include_router(monitor_stream_router)
    app.include_router(multi_preview_router)
    app.include_router(rtsp_manager_router)

    return app


app = create_app()


@app.get("/")
async def root() -> dict:
    """简单根路径，用于健康检查。"""
    return {"message": "Video Stream System Backend is running"}

