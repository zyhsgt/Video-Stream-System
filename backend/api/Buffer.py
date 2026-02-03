import subprocess
from backend.api.device_management.camera_registry import CameraRegistry

device_ip = "10.112.65.161"
# 获取 CameraRegistry 单例实例
_Camera_DB_PATH = "/mnt21t/home/zyh/Projects/Video-Stream-System/backend/DataBase/cameras_db_all_ucf_crime.pkl" # "/mnt21t/home/zyh/Projects/Video-Stream-System/backend/DataBase/cameras_db_test_server.pkl" # "D:\\python_proj\\Video-Stream-System\\backend\\DataBase\\cameras_db_test.pkl" # "/mnt21t/home/zyh/Projects/Video-Stream-System/backend/DataBase/cameras_db_test.pkl" # "../../DataBase/cameras_db_test.pkl"
_registry = CameraRegistry.get_instance(_Camera_DB_PATH) # 全局Cameras实例
_active_processes: dict[str, subprocess.Popen] = {} # rtsp url: ffmpeg进程