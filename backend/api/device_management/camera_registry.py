"""
摄像头注册表（内存管理器）。

CameraRegistry 负责在内存中管理所有 Camera 实例，提供增删改查、批量操作等功能。
"""

from __future__ import annotations

import asyncio
import pickle
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.api.Camera import Camera, CameraData


class CameraRegistry:
    """
    摄像头注册表（单例模式）。
    
    在内存中维护所有 Camera 实例，提供统一的增删改查接口。
    支持从持久化存储（pickle）加载/保存。
    """

    _instance: Optional[CameraRegistry] = None
    _lock = asyncio.Lock()

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """
        初始化注册表。
        
        Args:
            db_path: pickle 数据库路径，默认使用 cameras_db.pkl（与 Camera.py 同目录）
        """
        if db_path is None:
            # 默认路径：与 Camera.py 同目录
            db_path = Path(__file__).parent.parent / "cameras_db.pkl"
        self._db_path = Path(db_path)
        # 内存中的摄像头字典：{camera_id: Camera}
        self._cameras: Dict[str, Camera] = {}
        # 并发控制：批量 ping 时的信号量
        self._ping_semaphore = asyncio.Semaphore(5)

        # 后台定期检查任务（ping/流可用性）
        self._healthcheck_task: asyncio.Task | None = None
        self._healthcheck_interval_s: float = 30.0
        self._healthcheck_timeout_s: float = 5.0

        self.load_from_db()

    @classmethod
    def get_instance(cls, db_path: Optional[Path] = None) -> CameraRegistry:
        """
        获取单例实例。
        
        Args:
            db_path: 仅在首次创建时生效
        """
        if cls._instance is None:
            cls._instance = cls(db_path)
        return cls._instance

    # --- 基础 CRUD ---

    def add_camera(self, camera: Camera) -> None:
        """
        添加摄像头到内存注册表（若 camera_id 已存在则覆盖）。
        
        Args:
            camera: Camera 实例
        """
        self._cameras[camera.get_camera_id()] = camera

    def add_camera_from_data(self, data: CameraData | dict) -> Camera:
        """
        从数据结构创建 Camera 并添加到注册表。
        
        Args:
            data: CameraData 或字典
            
        Returns:
            创建的 Camera 实例
        """
        if isinstance(data, dict):
            # 转换为 CameraData
            data = CameraData(**data)
        
        camera = Camera(
            camera_id=data.camera_id,
            camera_ip=data.camera_ip,
            camera_name=data.camera_name,
            camera_location=data.camera_location,
            accessible=data.accessible,
            protocal_in=data.protocal_in,
            protocal_out=data.protocal_out,
        )
        self.add_camera(camera)
        return camera

    def remove_camera(self, camera_id: str) -> bool:
        """
        从注册表删除摄像头。
        
        Args:
            camera_id: 摄像头 ID
            
        Returns:
            成功删除返回 True，否则 False
        """
        if camera_id in self._cameras:
            del self._cameras[camera_id]
            return True
        return False

    def get_camera(self, camera_id: str) -> Optional[Camera]:
        """
        根据 camera_id 获取摄像头。
        
        Args:
            camera_id: 摄像头 ID
            
        Returns:
            Camera 实例，不存在返回 None
        """
        return self._cameras.get(camera_id)

    def get_all_cameras(self) -> List[Camera]:
        """
        获取所有摄像头列表。
        
        Returns:
            所有 Camera 实例的列表
        """
        return list(self._cameras.values())

    def get_camera_ids(self) -> List[str]:
        """
        获取所有摄像头 ID 列表。
        
        Returns:
            所有 camera_id 的列表
        """
        return list(self._cameras.keys())

    def has_camera(self, camera_id: str) -> bool:
        """
        检查摄像头是否存在。
        
        Args:
            camera_id: 摄像头 ID
            
        Returns:
            存在返回 True，否则 False
        """
        return camera_id in self._cameras

    def count(self) -> int:
        """
        获取摄像头总数。
        
        Returns:
            摄像头数量
        """
        return len(self._cameras)

    # --- 批量操作 ---

    async def ping_camera(self, camera_id: str, timeout_s: float = 5.0) -> Dict[str, Any]:
        """
        对指定摄像头执行一次 ping 检测。
        
        Args:
            camera_id: 摄像头 ID
            timeout_s: 超时时间（秒）
            
        Returns:
            ping 结果字典
            
        Raises:
            KeyError: 摄像头不存在
        """
        camera = self.get_camera(camera_id)
        if camera is None:
            raise KeyError(f"Camera not found: {camera_id}")
        
        async with self._ping_semaphore:
            try:
                result = await camera.ping_once(timeout_s=timeout_s)
                return result
            except Exception as e:
                return {
                    "Camera_Id": camera_id,
                    "Online": False,
                    "error": f"{type(e).__name__}: {e}",
                }

    async def ping_all_cameras(
        self, 
        timeout_s: float = 5.0,
        return_exceptions: bool = True
    ) -> Dict[str, Any]:
        """
        批量 ping 所有摄像头。
        
        Args:
            timeout_s: 每个摄像头的超时时间（秒）
            return_exceptions: 是否在结果中包含异常
            
        Returns:
            包含 total、results 的字典
        """
        cameras = self.get_all_cameras()
        if not cameras:
            return {"total": 0, "results": []}
        
        tasks = [
            self.ping_camera(cam.get_camera_id(), timeout_s=timeout_s)
            for cam in cameras
        ]
        results = await asyncio.gather(*tasks, return_exceptions=return_exceptions)
        
        return {
            "total": len(results),
            "results": results,
        }

    def start_periodic_healthcheck(
        self,
        interval_s: float = 30.0,
        timeout_s: float = 5.0,
    ) -> None:
        """
        启动后台定期健康检查任务。

        该任务会周期性对所有摄像头执行一次 `ping_once`（内部按 RTSP/HTTP 自动检测），
        并更新每个 Camera 的 `accessible/status_code/last_ping`。

        注意：需要在已有运行中的 asyncio event loop 中调用。
        """
        self._healthcheck_interval_s = float(interval_s)
        self._healthcheck_timeout_s = float(timeout_s)

        if self._healthcheck_task is not None and not self._healthcheck_task.done():
            return

        self._healthcheck_task = asyncio.create_task(self._healthcheck_loop())

    async def stop_periodic_healthcheck(self) -> None:
        """停止后台定期健康检查任务。"""
        if self._healthcheck_task is None:
            return

        task = self._healthcheck_task
        self._healthcheck_task = None
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def is_periodic_healthcheck_running(self) -> bool:
        """返回定期健康检查任务是否在运行。"""
        return self._healthcheck_task is not None and not self._healthcheck_task.done()

    async def run_healthcheck_once(
        self,
        timeout_s: float | None = None,
        return_exceptions: bool = True,
    ) -> Dict[str, Any]:
        """立即执行一次全量健康检查（不调度循环）。"""
        return await self.ping_all_cameras(
            timeout_s=self._healthcheck_timeout_s if timeout_s is None else float(timeout_s),
            return_exceptions=return_exceptions,
        )

    async def _healthcheck_loop(self) -> None:
        while True:
            start = time.monotonic()
            try:
                await self.run_healthcheck_once(return_exceptions=True)
            except asyncio.CancelledError:
                raise
            except Exception:
                # 保证后台任务不因单次异常退出
                pass
            elapsed = time.monotonic() - start
            elapsed = 0. # 不考虑ping的延迟?
            await asyncio.sleep(
                max(0, self._healthcheck_interval_s - elapsed) # 把单次ping的时间考虑到sleep内 (感觉把所有camera都ping一遍的延迟太长?)
            )

    def get_all_locations(self) -> List[Dict[str, Any]]:
        """
        获取所有摄像头的位置信息。
        
        Returns:
            包含 Camera_Name、Camera_Id、Camera_Loc 的字典列表
        """
        cameras = self.get_all_cameras()
        return [
            {
                "Camera_Name": cam.get_camera_name(),
                "Camera_Id": cam.get_camera_id(),
                "Camera_Loc": cam.get_camera_location(),
            }
            for cam in cameras
        ]

    def get_online_cameras(self) -> List[Camera]:
        """
        获取所有在线（accessible=True）的摄像头。
        
        Returns:
            在线摄像头列表
        """
        return [cam for cam in self._cameras.values() if cam.get_accessible()]

    def get_offline_cameras(self) -> List[Camera]:
        """
        获取所有离线（accessible=False）的摄像头。
        
        Returns:
            离线摄像头列表
        """
        return [cam for cam in self._cameras.values() if not cam.get_accessible()]

    # --- 持久化操作 ---

    def load_from_db(self) -> int:
        """
        从 pickle 数据库加载所有摄像头到内存。
        
        Returns:
            加载的摄像头数量
        """
        if not self._db_path.exists():
            return 0
        
        # try:
        with self._db_path.open("rb") as f:
            cameras: List[Camera] = pickle.load(f)

        # 清空现有数据并加载
        self._cameras.clear()
        for cam in cameras:
            self._cameras[cam.get_camera_id()] = cam

        return len(cameras)
        # except Exception:
        #     return 0

    def save_to_db(self) -> None:
        """
        将内存中的所有摄像头保存到 pickle 数据库。
        """
        cameras = self.get_all_cameras()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._db_path.open("wb") as f:
            pickle.dump(cameras, f)

    def reload_from_db(self) -> int:
        """
        重新从数据库加载（清空内存后加载）。
        
        Returns:
            加载的摄像头数量
        """
        self._cameras.clear()
        return self.load_from_db()

    # --- 统计信息 ---

    def get_stats(self) -> Dict[str, Any]:
        """
        获取注册表统计信息。
        
        Returns:
            包含总数、在线数、离线数等信息的字典
        """
        total = self.count()
        online = len(self.get_online_cameras())
        offline = len(self.get_offline_cameras())
        
        return {
            "total": total,
            "online": online,
            "offline": offline,
            "db_path": str(self._db_path),
        }

    def __repr__(self) -> str:
        return f"CameraRegistry(cameras={self.count()}, db_path={self._db_path})"


# _Camera_DB_PATH = "../../DataBase/cameras_db.pkl"
# camera_registry = CameraRegistry(db_path=_Camera_DB_PATH)
