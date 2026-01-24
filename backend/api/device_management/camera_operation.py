"""
摄像头操作 API（供前端使用）。

提供 FastAPI 路由接口，基于 CameraRegistry 实现摄像头的增删改查、持久化等操作。
"""

from __future__ import annotations

import pickle
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from backend.api.Camera import CameraData
from backend.api.device_management.camera_registry import CameraRegistry

router = APIRouter(prefix="/api/device", tags=["camera_operation"])

# 获取 CameraRegistry 单例实例
_Camera_DB_PATH = "../../DataBase/cameras_db.pkl"
_registry = CameraRegistry.get_instance(_Camera_DB_PATH)


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
    根据 camera_id 添加 Camera 实例到内存。
    
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
            "accessible",
            "protocol_in",
            "protocol_out",
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
    根据 camera_id 从内存中移除 Camera 实例。
    
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
                "protocal_in": cam.get_protocal_in(),
                "protocal_out": cam.get_protocal_out(),
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
    import asyncio

    async def _self_test() -> None:
        global _registry

        # 使用临时数据库路径，避免污染真实 DataBase/cameras_db.pkl
        tmp_db = "../../DataBase/cameras_db.pkl"
        with open(tmp_db, 'rb') as f:
            cameras = pickle.load(f)
            f.close()

        print(tmp_db)

        _registry = CameraRegistry.get_instance(tmp_db)

        # camera_id = "test_cam_002"
        #
        # print("[1] add_camera")
        add_payload = {
            "camera_id": camera_id,
            "camera_ip": "127.0.0.1",
            "camera_name": "SelfTestCam2",
            "camera_location": (1,1),
            "accessible": False,
            "protocol_in": "rtsp",
            "protocol_out": "http",
        }
        # r1 = await add_camera(add_payload)
        # print(r1)

        print("[2] list_all_cameras")
        r2 = await list_all_cameras()
        print(r2)

        print("[3] get_camera_stats")
        r3 = await get_camera_stats()
        print(r3)

        print("[4] get_all_cameras_status (会触发 ping_all_cameras)")
        r4 = await get_all_cameras_status()
        print(r4)

        print("[5] start_cameras_healthcheck")
        r5 = await start_cameras_healthcheck(interval_s=0.5, timeout_s=1.0)
        print(r5)

        print("[6] get_cameras_healthcheck_status")
        r6 = await get_cameras_healthcheck_status()
        print(r6)

        print("[7] run_cameras_healthcheck_once")
        r7 = await run_cameras_healthcheck_once(timeout_s=1.0)
        print(r7)


        while True:
            # print("[4] get_all_cameras_status (会触发 ping_all_cameras)")
            r4 = await get_all_cameras_status()
            print(r4)

        print("[8] stop_cameras_healthcheck")
        r8 = await stop_cameras_healthcheck()
        print(r8)

        print("[9] remove_camera")
        r9 = await remove_camera(camera_id)
        print(r9)

        print("[10] list_all_cameras (after remove)")
        r10 = await list_all_cameras()
        print(r10)

    asyncio.run(_self_test())
