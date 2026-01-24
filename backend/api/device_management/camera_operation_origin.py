import os
import asyncio
import pickle
from pathlib import Path
from typing import Any, Tuple, TypedDict, Union
from urllib.parse import urlparse
from fastapi import FastAPI, APIRouter

from device_ping import ping_once as _device_ping_once
from backend.api.Camera import Camera, CameraData

import random


_Camera_DB_PATH = "../../DataBase/cameras_db.pkl"

def _save_all(cameras: list["Camera"]) -> None:
    file = Path(_Camera_DB_PATH)
    file.parent.mkdir(parents=True, exist_ok=True)
    with file.open("wb") as f:
        pickle.dump(cameras, f)

def add_camera(camera: "Camera", _DB_PATH:str = _Camera_DB_PATH) -> None:
    """
    将摄像头对象追加到 pickle 数据库。
    若 camera_id 已存在则覆盖该条记录。
    """
    cameras = get_all_cameras(_DB_PATH) # ATTN: 增加摄像头时是否要从内存获取?
    cameras = [c for c in cameras if c.get_camera_id() != camera.get_camera_id()]
    cameras.append(camera)
    _save_all(cameras)

# 获取Camera_DB中所有的Camera
def get_all_cameras(DB_PATH):
    if not os.path.exists(DB_PATH):
        return []
    try:
        with open(DB_PATH, 'rb') as f:
            cameras = pickle.load(f)
            f.close()
    except Exception:
        return []

    return cameras

SEM = asyncio.Semaphore(5) # 并发上限控制最多同时ping5个?

# 一个Camera ping
async def ping_camera(camera: Camera):
    async with SEM:
        try:
            result = await camera.ping_once(timeout_s=10.)
        except Exception as e:
            result =  {
                "ok": False,
                "camera_id": getattr(camera, "id", None),
                "detail": f"{type(e).__name__}: {e}",
            }
        print(result)

        return result


router = APIRouter(prefix="/api/device", tags=["device_management"])

@router.get("/cameras/ping")
async def ping_cameras(cameras):
    # cameras: list[Camera] = get_all_cameras(Camera_DB_PATH)

    tasks = [ping_camera(cam) for cam in cameras]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    return {
        "total": len(results),
        "results": results,
    }

@router.get("/cameras/location")
async def get_cameras_location():
    cameras: list[Camera] = get_all_cameras(Camera_DB_PATH)

    all_locations = [
        {
            "Camera_Name": cam.get_camera_name(),
            "Camera_Id": cam.get_camera_id(),
            "Camera_Loc": cam.get_camera_location()
        } for cam in cameras
    ]

    return {
        "all_cameras_locations": all_locations
    }

@router.post("cameras/add_camera")
async def add_camera_from_data(data: Union[CameraData, dict]):
    """
    通过数据结构（字典）创建 Camera 实例并落盘。
    必填字段：camera_id、camera_ip、camera_name、camera_location(二元组经纬度)、
             accessible、protocal_in、protocal_out
    返回创建好的 Camera 实例。
    """
    payload: dict = dict(data)
    required = [
        "camera_id",
        "camera_ip",
        "camera_name",
        "camera_location",
        "accessible",
        "protocal_in",
        "protocal_out",
    ]
    missing = [k for k in required if k not in payload]
    if missing:
        raise ValueError(f"missing fields: {missing}")

    camera = Camera(
        camera_id=str(payload["camera_id"]),
        camera_ip=str(payload["camera_ip"]),
        camera_name=str(payload["camera_name"]),
        camera_location=tuple(payload["camera_location"]),  # type: ignore[arg-type]
        accessible=bool(payload["accessible"]),
        protocal_in=str(payload["protocal_in"]),
        protocal_out=str(payload["protocal_out"]),
    )
    add_camera(camera)

@router.delete("cameras/remove_camera/{camera_id}")
async def remove_camera(camera_id: str) -> bool:
    """
    按 camera_id 删除，成功删除返回 True，否则 False。
    """
    cameras = get_all_cameras(_Camera_DB_PATH)
    new_list = [c for c in cameras if c.get_camera_id() != camera_id]
    if len(new_list) == len(cameras):
        return {
            "Delite": False,
            "Info": f"没有找到摄像头:{camera_id}"
        }
    _save_all(new_list)
    return {
        "Delite": True,
        "Info": f"摄像头{camera_id}被成功删除"
    }


# ATTN: main and run just for testing
async def main():
    cameras = get_all_cameras(_Camera_DB_PATH)
    location = await get_cameras_location(cameras)
    result = await ping_cameras(cameras)
    print({
        "Location": location,
        "Total_Cameras": result["total"],
        "Ping_Results": result["results"]
    })

def run():
    asyncio.run(main())

if __name__ == "__main__":
    # 简单演示：创建一台摄像头，保存并执行同步 ping
    # demo_data: CameraData = {
    #     "camera_id": "123456",
    #     "camera_ip": "127.0.0.1",
    #     "camera_name": "Camera_Test2",
    #     "camera_location": (0.0, 0.0),
    #     "accessible": False,
    #     "protocal_in": "rtsp://127.0.0.1:8554/live/camera2",
    #     "protocal_out": "None",
    # }
    #
    # cam = add_camera_from_data(demo_data)
    # print("Before ping:", cam.get_accessible(), cam.get_status_code())
    # try:
    #     res = cam.ping_once_sync(timeout_s=10.0)
    #     print("Ping result:", res)
    # except Exception as exc:  # pragma: no cover
    #     print(f"Ping failed: {exc}")

    run()
