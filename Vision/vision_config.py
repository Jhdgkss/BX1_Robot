"""
BX1 PC VISION SETTINGS
======================

Technical settings for the PC-side video receiver and YOLO processor.

The robot-side camera streamer will later send JPEG frames to:
    ws://<BRAIN_PC_IP>:VIDEO_PORT
"""

VIDEO_HOST = "0.0.0.0"
VIDEO_PORT = 8772

# Reject unexpectedly large frames before allocating more processing.
MAX_JPEG_BYTES = 4 * 1024 * 1024

# YOLO processing.
YOLO_ENABLED = True

# Ultralytics model name/path.
# yolo11n.pt is intentionally small for real-time use.
YOLO_MODEL = "yolo11n.pt"

YOLO_CONFIDENCE = 0.35
YOLO_IOU = 0.45

# Do not process every incoming video frame.
# The GUI can still display the full received stream while YOLO runs
# at a lower rate to keep GPU/CPU use sensible.
YOLO_MAX_FPS = 3.0

# Model inference size.
YOLO_IMAGE_SIZE = 640
