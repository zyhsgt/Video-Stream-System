"""
设备管理相关API
功能：
- 监控设备状态
- 设备分布地域图
- 设备监控（ping检测、注册管理）

示例：
- /api/device/hello 返回 hello world
"""

from .hello_world import router
from .device_state import router as device_state_router
from .device_monitor import router as device_monitor_router