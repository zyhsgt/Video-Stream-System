"""
视频流传输相关API
功能：
- 监控流选择与预览
- 多设备监控预览
- 视频导出
- 历史视频存储/回放
- RTSP流管理
"""

from .monitor_stream import router as monitor_stream_router
from .multi_preview import router as multi_preview_router
from .rtsp_manager import router as rtsp_manager_router



