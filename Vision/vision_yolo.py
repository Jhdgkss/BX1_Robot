"""
BX1 YOLO Visual Processor - PC Side
====================================

Receives JPEG frames from Master_Main_GUI.py and performs YOLO object
detection on the PC.

This module never talks directly to the robot or GUI.

    IncomingVideoServer
            |
            v
    Master_Main_GUI.py
            |
            v
    YOLOVisualProcessor
            |
            v
    Master_Main_GUI.py
            |
            v
         GUIController

The queue is latest-frame-only. If YOLO is busy, stale frames are
discarded rather than building an ever-growing video backlog.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Callable, Dict, Optional


class YOLOVisualProcessor:
    def __init__(
        self,
        *,
        model_name: str = "yolo11n.pt",
        confidence: float = 0.35,
        iou: float = 0.45,
        image_size: int = 640,
        max_fps: float = 3.0,
        result_callback: Optional[
            Callable[[bytes, Dict], None]
        ] = None,
        status_callback: Optional[
            Callable[[Dict], None]
        ] = None,
    ):
        self.model_name = str(model_name)
        self.confidence = float(confidence)
        self.iou = float(iou)
        self.image_size = int(image_size)
        self.max_fps = max(
            0.1,
            float(max_fps),
        )

        self.result_callback = result_callback
        self.status_callback = status_callback

        self._queue = queue.Queue(
            maxsize=1
        )

        self._stop_event = threading.Event()
        self._enabled = threading.Event()
        self._enabled.set()

        self._thread = None
        self._model = None
        self._model_error = None

        self._last_inference_started = 0.0

    def _publish_status(
        self,
        event: str,
        **extra,
    ):
        packet = {
            "event": str(event),
            "enabled": self.enabled,
            "model": self.model_name,
            "timestamp": time.time(),
            **extra,
        }

        if callable(self.status_callback):
            self.status_callback(packet)

    @property
    def enabled(self) -> bool:
        return self._enabled.is_set()

    def set_enabled(
        self,
        enabled: bool,
    ):
        if enabled:
            self._enabled.set()
            self._publish_status(
                "yolo_enabled"
            )
        else:
            self._enabled.clear()
            self._publish_status(
                "yolo_paused"
            )

    def start(self):
        if (
            self._thread is not None
            and self._thread.is_alive()
        ):
            return

        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._worker,
            daemon=True,
            name="BX1-YOLO",
        )
        self._thread.start()

    def stop(self):
        self._stop_event.set()

        try:
            self._queue.put_nowait(
                None
            )
        except queue.Full:
            pass

        if (
            self._thread is not None
            and self._thread.is_alive()
        ):
            self._thread.join(
                timeout=3.0
            )

        self._thread = None

    def submit_frame(
        self,
        jpeg_bytes: bytes,
        metadata: Optional[Dict] = None,
    ):
        if not self.enabled:
            return False

        packet = (
            bytes(jpeg_bytes),
            dict(metadata or {}),
        )

        # Latest-frame-only queue.
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass

        try:
            self._queue.put_nowait(
                packet
            )
            return True

        except queue.Full:
            return False

    def _load_model(self):
        if self._model is not None:
            return True

        if self._model_error is not None:
            return False

        self._publish_status(
            "yolo_loading"
        )

        try:
            from ultralytics import YOLO

            self._model = YOLO(
                self.model_name
            )

            self._publish_status(
                "yolo_ready"
            )
            return True

        except Exception as exc:
            self._model_error = (
                f"{type(exc).__name__}: {exc}"
            )

            self._publish_status(
                "yolo_unavailable",
                error=self._model_error,
            )

            return False

    def _worker(self):
        self._publish_status(
            "yolo_worker_started"
        )

        while not self._stop_event.is_set():
            try:
                packet = self._queue.get(
                    timeout=0.25
                )
            except queue.Empty:
                continue

            if packet is None:
                continue

            if not self.enabled:
                continue

            min_interval = (
                1.0 / self.max_fps
            )

            now = time.perf_counter()
            wait_for = (
                min_interval
                - (
                    now
                    - self._last_inference_started
                )
            )

            if wait_for > 0:
                if self._stop_event.wait(
                    wait_for
                ):
                    break

            jpeg_bytes, source_metadata = packet

            if not self._load_model():
                continue

            try:
                import cv2
                import numpy as np

                buffer = np.frombuffer(
                    jpeg_bytes,
                    dtype=np.uint8,
                )

                frame = cv2.imdecode(
                    buffer,
                    cv2.IMREAD_COLOR,
                )

                if frame is None:
                    self._publish_status(
                        "yolo_frame_decode_error"
                    )
                    continue

                self._last_inference_started = (
                    time.perf_counter()
                )

                results = self._model.predict(
                    source=frame,
                    conf=self.confidence,
                    iou=self.iou,
                    imgsz=self.image_size,
                    verbose=False,
                )

                inference_ms = (
                    (
                        time.perf_counter()
                        - self._last_inference_started
                    )
                    * 1000.0
                )

                if not results:
                    continue

                result = results[0]

                detections = []

                names = getattr(
                    result,
                    "names",
                    {},
                )

                boxes = getattr(
                    result,
                    "boxes",
                    None,
                )

                if boxes is not None:
                    for box in boxes:
                        cls_value = int(
                            box.cls[0].item()
                        )
                        confidence = float(
                            box.conf[0].item()
                        )

                        xyxy = [
                            float(value)
                            for value in (
                                box.xyxy[0]
                                .detach()
                                .cpu()
                                .tolist()
                            )
                        ]

                        detections.append(
                            {
                                "class_id": cls_value,
                                "class_name": str(
                                    names.get(
                                        cls_value,
                                        cls_value,
                                    )
                                ),
                                "confidence": round(
                                    confidence,
                                    4,
                                ),
                                "xyxy": [
                                    round(value, 1)
                                    for value in xyxy
                                ],
                            }
                        )

                annotated = result.plot()

                ok, encoded = cv2.imencode(
                    ".jpg",
                    annotated,
                    [
                        int(
                            cv2.IMWRITE_JPEG_QUALITY
                        ),
                        85,
                    ],
                )

                if not ok:
                    continue

                annotated_jpeg = (
                    encoded.tobytes()
                )

                info = {
                    "timestamp": time.time(),
                    "model": self.model_name,
                    "inference_ms": round(
                        inference_ms,
                        1,
                    ),
                    "detection_count": len(
                        detections
                    ),
                    "detections": detections,
                    "source": source_metadata,
                }

                if callable(
                    self.result_callback
                ):
                    self.result_callback(
                        annotated_jpeg,
                        info,
                    )

            except Exception as exc:
                self._publish_status(
                    "yolo_processing_error",
                    error=(
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
                )

        self._publish_status(
            "yolo_worker_stopped"
        )
