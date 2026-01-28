"""
FastAPI 应用入口。

在这里创建 FastAPI 实例，并挂载各个子路由。

启动命令（在项目根目录 `Video-Stream-System` 下执行）：

    uvicorn backend.main:app --reload

"""
import asyncio

from fastapi import FastAPI
import uvicorn
# 设备管理模块
#from backend.api.device_management.hello_world import router as hello_world_router
# from backend.api.device_management.device_state import router as device_state_router
# from backend.api.device_management.device_monitor import router as device_monitor_router

# 视频流模块
# from backend.api.video_stream.monitor_stream import router as monitor_stream_router
# from backend.api.video_stream.multi_preview import router as multi_preview_router
# from backend.api.video_stream.rtsp_manager import router as rtsp_manager_router

from backend.api.device_management.camera_operation import router as camera_operation_router
from backend.api.device_management.camera_operation import load_cameras_from_db, save_cameras_to_db, start_cameras_healthcheck, stop_cameras_healthcheck


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。"""
    app = FastAPI(
        title="视频轮播系统后端",
        version="1.0.0",
    )

    # 注册路由
    app.include_router(camera_operation_router)


    return app

app = create_app()


if __name__ == '__main__':
    asyncio.run(load_cameras_from_db())
    asyncio.run(start_cameras_healthcheck())
    uvicorn.run(app="main:app", host="127.0.0.1", port=8000)
    asyncio.run(stop_cameras_healthcheck())
    asyncio.run(save_cameras_to_db())

