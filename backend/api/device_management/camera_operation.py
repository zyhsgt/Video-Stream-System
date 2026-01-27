"""
摄像头操作 API（供前端使用）。

提供 FastAPI 路由接口，基于 CameraRegistry 实现摄像头的增删改查、持久化等操作。
"""

from __future__ import annotations

import pickle
import random
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from backend.api.Camera import CameraData, Camera
from backend.api.device_management.camera_registry import CameraRegistry
from backend.api.video_stream.rtsp_manager import StartStreamRequest, StopStreamRequest, start_stream, stop_stream
from backend.api.video_stream.camera_stream import convert_rtsp_to_hls, convert_rtsp_to_flv, convert_rtsp_to_webrtc

from backend.api.Buffer import _registry, _active_processes

router = APIRouter(prefix="/api/device", tags=["camera_operation"])

@router.post("/cameras/simulate_camera_from_video")
async def simulate_cameras_from_video(data: CameraData) -> Dict[str, Any]: # (实例化摄像头类)根据本地视频模拟摄像头
    try:
        # 1) 规范化为 list 并校验长度一致
        def _as_list(v: Any) -> List[Any]:
            return [v] if isinstance(v, str) or not isinstance(v, list) else list(v)

        camera_ids = _as_list(data.camera_id)
        camera_ips = _as_list(data.camera_ip)
        camera_names = _as_list(data.camera_name)
        camera_locs = _as_list(data.camera_location)
        video_paths = _as_list(data.video_path)

        n = len(camera_ids)
        if not (len(camera_ips) == len(camera_names) == len(camera_locs) == len(video_paths) == n):
            raise HTTPException(
                status_code=400,
                detail=(
                    "CameraData 中 camera_id/camera_ip/camera_name/camera_location/video_path 长度必须一致: "
                    f"{len(camera_ids)}/{len(camera_ips)}/{len(camera_names)}/{len(camera_locs)}/{len(video_paths)}"
                ),
            )

        # 2) 校验 camera_id 不重复
        ids_str = [str(x) for x in camera_ids]
        dup_ids = sorted({x for x in ids_str if ids_str.count(x) > 1})
        if dup_ids:
            raise HTTPException(status_code=400, detail=f"camera_id 存在重复: {dup_ids}")

        created: List[Dict[str, Any]] = []

        for camera_id, camera_name, camera_ip, camera_loc, video_path in zip(
            ids_str,
            camera_names,
            camera_ips,
            camera_locs,
            video_paths,
        ):
            # 3) 构建 StartStreamRequest 并启动流, 获取rtsp_url
            req = StartStreamRequest( # 这里暂时先使用单个请求, 这个数据结构和start_stream也支持一次进行多个请求
                camera_id=camera_id,
                camera_name=camera_name,
                host=camera_ip,
                video_path=video_path,
            )
            stream_resp = await start_stream(req)
            rtsp_url = stream_resp.get("rtsp_url")
            if not rtsp_url:
                raise HTTPException(status_code=500, detail=f"start_stream 未返回 rtsp_url: {stream_resp}")

            # 4) 获取前端使用的视频流url WebRTC/FLV/HLS
            if data.protocol_out == None or data.protocol_out.strip():
                rtsp_stream_name = rtsp_url.split("/")[-1] # or f"{data.camera_name}_{data.camera_id}"
                webrtc_url = convert_rtsp_to_webrtc(rtsp_stream_name, None) # 目前先暂定使用WebRTC

            # 4) 使用 rtsp_url 作为 protocol_in 实例化 Camera，并注册
            cam = Camera(
                camera_id=camera_id,
                camera_ip=camera_ip,
                camera_name=camera_name,
                camera_location=camera_loc,
                video_path=video_path,
                accessible=False,
                protocol_in=rtsp_url,
                protocol_out=webrtc_url,
            )

            if _registry.has_camera(camera_id):
                raise HTTPException(status_code=409, detail=f"摄像头 ID {camera_id} 已存在")

            _registry.add_camera(cam)

            created.append(
                {
                    "camera_id": camera_id,
                    "camera_name": camera_name,
                    "camera_ip": camera_ip,
                    "video_path": video_path,
                    "protocol_in": rtsp_url,
                }
            )

        return {
            "success": True,
            "total": len(created),
            "cameras": created,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"模拟摄像头失败: {str(e)}")

@router.post("/cameras/load_from_db")
async def load_cameras_from_db() -> Dict[str, Any]:
    """
    从数据库中读取所有 Camera 实例到内存。
    
    Returns:
        包含加载数量和状态的字典
    """
    try:
        count = _registry.load_from_db()
        return {
            "success": True,
            "message": f"成功从数据库加载 {count} 个摄像头",
            "loaded_count": count,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"加载失败: {str(e)}")


@router.post("/cameras/save_to_db")
async def save_cameras_to_db() -> Dict[str, Any]:
    """
    将当前内存中的所有 Camera 实例保存到数据库。
    
    Returns:
        包含保存数量和状态的字典
    """
    try:
        count = _registry.count()
        _registry.save_to_db()
        return {
            "success": True,
            "message": f"成功保存 {count} 个摄像头到数据库",
            "saved_count": count,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


@router.post("/cameras/add")
async def add_camera(data: CameraData | Dict[str, Any]) -> Dict[str, Any]:
    """
    根据 camera_id 添加 Camera 实例到内存 但是并没有保存到临时数据库。

    Args:
        data: CameraData 或字典，包含摄像头信息

    Returns:
        包含添加结果和摄像头信息的字典
    """
    print("In add_camera")
    try:
        # 转换为字典格式
        if isinstance(data, CameraData):
            payload = data.model_dump()
        else:
            payload = dict(data)

        # 检查必填字段
        required = [
            "camera_id",
            "camera_ip",
            "camera_name",
            "camera_location",
            "video_path", # 目前从本地视频模拟摄像头需要指定一个视频路径
            "accessible",
            # "protocol_in", # ATTN: 目前通过视频模拟摄像头protocol_in/out不用自己定义?直接生成吗? 因为rtsp_url写死了是: rtsp://ip:port/live/{camera_name}_{camera_id}
            # "protocol_out",
        ]
        missing = [k for k in required if k not in payload]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"缺少必填字段: {missing}",
            )

        # 检查 camera_id 是否已存在
        camera_id = str(payload["camera_id"])
        if _registry.has_camera(camera_id):
            raise HTTPException(
                status_code=409,
                detail=f"摄像头 ID {camera_id} 已存在",
            )

        if payload["protocol_in"] == None:
            # 使用 rtsp_manager.start_stream 启动推流
            req = StartStreamRequest(
                camera_id=payload['camera_id'],
                camera_name=payload['camera_name'],
                video_path=payload['video_path'],
                host=payload['camera_ip'],
            )
            stream_resp = await start_stream(req) # 这里直接启动对应的rtsp url并保存在内存中
            rtsp_url = stream_resp.get("rtsp_url")
            if not rtsp_url:
                raise HTTPException(status_code=500, detail=f"rtsp_manager.start_stream 未返回 rtsp_url: {stream_resp}")

            payload['protocol_in'] = rtsp_url

        if payload['protocol_out'] == None:
            if rtsp_url != None:
                rtsp_stream_name = f"{payload['camera_name']}_{payload['camera_id']}"
                webrtc_url = convert_rtsp_to_webrtc(rtsp_stream_name, None)  # 目前先暂定使用WebRTC
                payload['protocol_out'] = webrtc_url

        # 创建并添加摄像头
        camera = _registry.add_camera_from_data(payload)

        return {
            "success": True,
            "message": f"成功添加摄像头: {camera_id}",
            "camera_id": camera_id,
            "camera_name": camera.get_camera_name(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加失败: {str(e)}")


@router.delete("/cameras/remove/{camera_id}")
async def remove_camera(camera_id: str) -> Dict[str, Any]:
    """
    根据 camera_id 从内存中移除 Camera 实例 但是没有从临时数据库中移除。

    Args:
        camera_id: 摄像头 ID

    Returns:
        包含删除结果的字典
    """
    try:
        if not _registry.has_camera(camera_id):
            return {
                "success": True,
                "message": f"摄像头{camera_id}不存在"
            }

        success = _registry.remove_camera(camera_id)
        if success:
            return {
                "success": True,
                "message": f"成功删除摄像头: {camera_id}",
                "camera_id": camera_id,
            }
        else:
            return{
                "success": False,
                "message": f"删除摄像头{camera_id}失败",
                "camera_id": camera_id
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")

@router.get("/cameras/protocol_out/{camera_id}") # 可能并不太需要,所有信息都可以从get_camera_status获取
async def get_camera_protocol_out(camera_id: str) -> Dict[str, Any]:
    """
    通过 camera_id 查询 Camera 的 protocol_out。

    返回字段：camera_id、camera_name、protocol_out
    """
    try:
        camera = _registry.get_camera(camera_id=camera_id)
        if camera is None:
            return {
                "success": False,
                "camera": f"没有找到摄像头：{camera_id}",
            }

        return {
            "success": True,
            "camera": {
                "camera_id": camera.get_camera_id(),
                "camera_name": camera.get_camera_name(),
                "protocol_out": camera.get_protocol_out(),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取 protocol_out 失败: {str(e)}")


@router.post("/cameras/stream/start/{camera_id}")
async def start_camera_stream(camera_id: str) -> Dict[str, Any]:
    """通过 camera_id 启动某个 Camera 的 RTSP 推流（调用 rtsp_manager.start_stream）。"""
    try:
        camera = _registry.get_camera(camera_id=camera_id)
        if camera is None:
            raise HTTPException(status_code=404, detail=f"没有找到摄像头：{camera_id}")

        # 使用 rtsp_manager.start_stream 启动推流
        req = StartStreamRequest(
            camera_id=camera.get_camera_id(),
            camera_name=camera.get_camera_name(),
            video_path=camera.get_video_path(),
            host=camera.get_camera_ip(),
        )
        stream_resp = await start_stream(req)
        rtsp_url = stream_resp.get("rtsp_url")
        if not rtsp_url:
            raise HTTPException(status_code=500, detail=f"rtsp_manager.start_stream 未返回 rtsp_url: {stream_resp}")

        # 更新 camera 实例的 protocol_in
        camera.set_protocol_in(rtsp_url)
        
        await asyncio.sleep(0.1)
        return {
            "success": True,
            "message": "启动推流成功",
            "camera": {
                "camera_id": camera.get_camera_id(),
                "camera_name": camera.get_camera_name(),
                "protocol_in": camera.get_protocol_in(),
                "rtsp_url": rtsp_url,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动推流失败: {str(e)}")


@router.post("/cameras/stream/stop/{camera_id}")
async def stop_camera_stream(camera_id: str) -> Dict[str, Any]:
    """通过 camera_id 停止某个 Camera 的 RTSP 推流（调用 rtsp_manager.stop_stream）。"""
    try:
        camera = _registry.get_camera(camera_id=camera_id)
        if camera is None:
            raise HTTPException(status_code=404, detail=f"没有找到摄像头：{camera_id}")

        stream_name = f"{camera.get_camera_name()}_{camera.get_camera_id()}"
        resp = await stop_stream(StopStreamRequest(stream_name=stream_name))

        return {
            "success": True,
            "message": "停止推流成功",
            "rtsp_manager": resp,
            "camera": {
                "camera_id": camera.get_camera_id(),
                "camera_name": camera.get_camera_name(),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"停止推流失败: {str(e)}")

@router.get("/cameras/one_status/{camera_id}")
async def get_camera_status(camera_id:str) -> Dict[str, Any]:
    '''
    获取camera_id的实例的基本信息,
    return: {
        "success": True or False,
        "camera_status": "没有找到摄像头" or status_dict
    }
    '''
    try:
        # 先执行批量 ping 获取最新状态
        ping_result = await _registry.ping_camera(camera_id=camera_id, timeout_s=5.0)

        # 获取所有摄像头信息
        camera = _registry.get_camera(camera_id=camera_id)
        if camera == None:
            return {
                "success": False,
                "camera_status": f"没有找到摄像头：{camera_id}"
            }

        is_online = False
        if ping_result:
            is_online = ping_result.get("Online", False)
        else:
            is_online = camera.get_accessible()

        status = {
            "camera_id": camera_id,
            "camera_name": camera.get_camera_name(),
            "is_online": is_online,
            "camera_ip": camera.get_camera_ip(),
            "camera_location": camera.get_camera_location(),
            "video_path": camera.get_video_path(),
            "protocol_in": camera.get_protocol_in(),
            "protocol_out": camera.get_protocol_out(),
            "status_code": camera.get_status_code(),  # not use
        }

        return {
            "success": True,
            "camera_status": status,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")

@router.get("/cameras/status")
async def get_all_cameras_status() -> Dict[str, Any]:
    """
    获取当前所有 Camera 实例的在线状态。

    包括：camera 的名称、id、以及是否在线。
    会对所有摄像头执行 ping 检测以获取最新状态。

    Returns:
        包含所有摄像头状态信息的字典
    """
    try:
        # 先执行批量 ping 获取最新状态
        ping_results = await _registry.ping_all_cameras(timeout_s=5.0)

        # 获取所有摄像头信息
        cameras = _registry.get_all_cameras()

        # 构建状态列表
        status_list: List[Dict[str, Any]] = []
        for camera in cameras:
            camera_id = camera.get_camera_id()

            # 从 ping 结果中查找对应的结果
            ping_result = None
            for result in ping_results.get("results", []):
                if isinstance(result, dict) and result.get("Camera_Id") == camera_id: # 拿到某个camera的result
                    ping_result = result
                    break

            # 确定在线状态：优先使用 ping 结果，否则使用 camera 的 accessible 属性
            is_online = False
            if ping_result:
                is_online = ping_result.get("Online", False)
            else:
                is_online = camera.get_accessible()

            status_list.append({
                "camera_id": camera_id,
                "camera_name": camera.get_camera_name(),
                "is_online": is_online,
                "camera_ip": camera.get_camera_ip(),
                "camera_location": camera.get_camera_location(),
                "video_path": camera.get_video_path(),
                "protocol_in": camera.get_protocol_in(),
                "protocol_out": camera.get_protocol_out(),
                "status_code": camera.get_status_code(), # not use
            })

        return {
            "success": True,
            "total": len(status_list),
            "cameras": status_list,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")


@router.get("/cameras/list")
async def list_all_cameras() -> Dict[str, Any]:
    """
    获取当前内存中所有 Camera 实例的基本信息（不执行 ping）。

    Returns:
        包含所有摄像头基本信息的字典
    """
    try:
        cameras = _registry.get_all_cameras()
        camera_list = [
            {
                "camera_id": cam.get_camera_id(),
                "camera_name": cam.get_camera_name(),
                "camera_ip": cam.get_camera_ip(),
                "camera_location": cam.get_camera_location(),
                "accessible": cam.get_accessible(),
                "protocal_in": cam.get_protocol_in(),
                "protocal_out": cam.get_protocol_out(),
            }
            for cam in cameras
        ]

        return {
            "success": True,
            "total": len(camera_list),
            "cameras": camera_list,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取列表失败: {str(e)}")


@router.get("/cameras/stats")
async def get_camera_stats() -> Dict[str, Any]:
    """
    获取摄像头统计信息。

    Returns:
        包含总数、在线数、离线数等统计信息的字典
    """
    try:
        stats = _registry.get_stats()
        return {
            "success": True,
            **stats,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")


@router.post("/cameras/healthcheck/start")
async def start_cameras_healthcheck(interval_s: float = 30.0, timeout_s: float = 5.0) -> Dict[str, Any]:
    """启动后台定期健康检查（RTSP/HTTP 可用性检测）。"""
    try:
        _registry.start_periodic_healthcheck(interval_s=interval_s, timeout_s=timeout_s)
        return {
            "success": True,
            "running": _registry.is_periodic_healthcheck_running(),
            "interval_s": float(interval_s),
            "timeout_s": float(timeout_s),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动健康检查失败: {str(e)}")


@router.post("/cameras/healthcheck/stop")
async def stop_cameras_healthcheck() -> Dict[str, Any]:
    """停止后台定期健康检查。"""
    try:
        await _registry.stop_periodic_healthcheck()
        return {
            "success": True,
            "running": _registry.is_periodic_healthcheck_running(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"停止健康检查失败: {str(e)}")


@router.get("/cameras/healthcheck/status")
async def get_cameras_healthcheck_status() -> Dict[str, Any]:
    """查询后台定期健康检查是否在运行。"""
    try:
        return {
            "success": True,
            "running": _registry.is_periodic_healthcheck_running(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取健康检查状态失败: {str(e)}")


@router.post("/cameras/healthcheck/run_once")
async def run_cameras_healthcheck_once(timeout_s: float = 5.0) -> Dict[str, Any]:
    """手动触发一次全量健康检查（立即 ping/检查流可用性）。"""
    try:
        result = await _registry.run_healthcheck_once(timeout_s=timeout_s, return_exceptions=True)
        return {
            "success": True,
            **result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"执行健康检查失败: {str(e)}")


if __name__ == "__main__":

    # camera_path = "../../DataBase/cameras_db_test.pkl"
    # with open(camera_path, 'rb') as f:
    #     cameras_list = pickle.load(f)
    #     f.close()
    #
    # print(len(cameras_list))

    import asyncio
    import os

    locations = [
        (116.36291593, 39.96611858),
        (116.36248302, 39.96601564),
        (116.36293416, 39.96601168),
        (116.36357201, 39.96622150),
        (116.36343326, 39.96603486),
        (116.36366866, 39.96634863),
        (116.36305880, 39.96595619),
        (116.36292583, 39.96764021),
        (116.36416222, 39.96625725),
        (116.36292723, 39.96694601)
    ]

    test_video_path = os.getenv(
        "CAMERA_SELFTEST_VIDEO_PATH",
        "F:\\UCF-Crime\\UCF-Crime-test\\Normal_Videos_935_x264.mp4",
    )

    async def _self_test() -> None:
        global _registry

        # 使用临时数据库路径，避免污染真实 DataBase/cameras_db.pkl
        tmp_db = os.getenv("CAMERA_SELFTEST_DB", "../../DataBase/cameras_db_test.pkl")

        # camera_names = []
        # camera_ids = []
        # camera_ip = []
        # camera_loc = []
        # video_path = []
        # for i in range(0, 10):
        #     camera_names.append(f"Camera{i}")
        #     camera_ids.append(str(random.randint(99999, 1000000)))
        #     camera_ip.append("127.0.0.1")
        #     camera_loc.append(locations[i])
        #     video_path.append(test_video_path)
        #
        # cam_data = CameraData(
        #     camera_id = camera_ids,
        #     camera_ip = camera_ip,
        #     camera_name = camera_names,
        #     camera_location = camera_loc,
        #     video_path = video_path
        # )
        #
        # await simulate_cameras_from_video(cam_data)
        # _registry.save_to_db()

        _registry = CameraRegistry.get_instance(tmp_db)

        # camera_id = os.getenv("CAMERA_SELFTEST_CAMERA_ID", "test_cam_002")

        print("[1] load_cameras_from_db")
        r0 = await load_cameras_from_db()
        print(r0)

        # print("[2] add_camera")
        # add_payload = {
        #     "camera_id": camera_id,
        #     "camera_ip": "127.0.0.1",
        #     "camera_name": "SelfTestCam2",
        #     "camera_location": (1, 1),
        #     "video_path": test_video_path,
        #     "accessible": False,
        #     "protocol_in": "rtsp",
        #     "protocol_out": "http",
        # }
        # r1 = await add_camera(add_payload)
        # print(r1)

        print("[3] list_all_cameras")
        r2 = await list_all_cameras()
        print(r2)

        print("[4] get_camera_stats")
        r3 = await get_camera_stats()
        print(r3)

        print("[5] get_all_cameras_status (会触发 ping_all_cameras)")
        r4 = await get_all_cameras_status()
        camera_id_list = [cam["camera_id"] for cam in r4['cameras']]
        print(r4)

        print("[6] start_cameras_healthcheck")
        r5 = await start_cameras_healthcheck(interval_s=0.5, timeout_s=1.0)
        print(r5)

        print("[7] get_cameras_healthcheck_status")
        r6 = await get_cameras_healthcheck_status()
        print(r6)

        print("[8] run_cameras_healthcheck_once")
        r7 = await run_cameras_healthcheck_once(timeout_s=1.0)
        print(r7)

        selected_cameras_id = camera_id_list[4:9]

        for camera_id in selected_cameras_id:
            print("[9] start_camera_stream")
            r_start = await start_camera_stream(camera_id)
            print(r_start)

            # ping_camera_result = await get_camera_status(camera_id)
            # print(ping_camera_result)
            # await asyncio.sleep(0.1)
            r7 = await run_cameras_healthcheck_once(timeout_s=1.0)
            print(r7)

        for camera_id in selected_cameras_id:
            print("[10] stop_camera_stream")
            r_stop = await stop_camera_stream(camera_id)
            print(r_stop)
            # await asyncio.sleep(1)
            r7 = await run_cameras_healthcheck_once(timeout_s=1.0)
            print(r7)

        loops = int(os.getenv("CAMERA_SELFTEST_STATUS_LOOPS", "0"))
        if loops > 0:
            for _ in range(loops):
                r = await get_all_cameras_status()
                print(r)

        print("[11] stop_cameras_healthcheck")
        r8 = await stop_cameras_healthcheck()
        print(r8)

        print("[12] remove_camera")
        r9 = await remove_camera(camera_id)
        print(r9)

        print("[13] list_all_cameras (after remove)")
        r10 = await list_all_cameras()
        print(r10)

        print("[14] save_cameras_to_db")
        r11 = await save_cameras_to_db()
        print(r11)

    asyncio.run(_self_test())
