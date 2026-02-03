import asyncio
import os
from backend.api.device_management.camera_operation import load_cameras_from_db


async def _self_test() -> None:
    # global _registry

    # 使用临时数据库路径，避免污染真实 DataBase/cameras_db.pkl
    tmp_db = os.getenv("CAMERA_SELFTEST_DB", "DataBase/cameras_db_test.pkl")

    # _registry = CameraRegistry.get_instance(tmp_db)

    camera_id = os.getenv("CAMERA_SELFTEST_CAMERA_ID", "test_cam_002")

    print("[1] load_cameras_from_db")
    r0 = await load_cameras_from_db()
    print(r0)


asyncio.run(_self_test())