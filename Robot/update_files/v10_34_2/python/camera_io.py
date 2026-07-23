from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


@dataclass
class CameraConfig:
    camera_index: int = 0
    camera_device: str = "/dev/video0"
    jpeg_quality: int = 85


class CameraCapture:
    """Thread-safe camera capture with optional lightweight local awareness.

    Snapshot capture still works through fswebcam when OpenCV is unavailable.
    Face and motion awareness deliberately degrade gracefully because OpenCV is
    optional on the UNO Q.
    """

    def __init__(self, cfg: CameraConfig) -> None:
        self.cfg = cfg
        self._cv2 = None
        self._lock = threading.RLock()
        self._previous_gray = None
        self._face_cascade = None
        self._last_probe: Dict[str, Any] = {}
        try:
            import cv2  # type: ignore

            self._cv2 = cv2
            try:
                cascade_path = str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
                cascade = cv2.CascadeClassifier(cascade_path)
                if cascade is not None and not cascade.empty():
                    self._face_cascade = cascade
            except Exception:
                self._face_cascade = None
        except Exception:
            self._cv2 = None

    @property
    def opencv_available(self) -> bool:
        return self._cv2 is not None

    @property
    def face_detection_available(self) -> bool:
        return self._cv2 is not None and self._face_cascade is not None

    def _open_capture_locked(self):  # type: ignore[no-untyped-def]
        cv2 = self._cv2
        if cv2 is None:
            raise RuntimeError("OpenCV is not available")

        candidates: list[Any] = []
        device = str(self.cfg.camera_device or "").strip()
        if device:
            candidates.append(device)
        try:
            index = int(self.cfg.camera_index)
        except Exception:
            index = 0
        if index not in candidates:
            candidates.append(index)

        last_error = ""
        for candidate in candidates:
            # On Linux, explicitly request V4L2 first. Generic VideoCapture was
            # selecting GStreamer, failing, printing warnings every few seconds
            # and consuming enough CPU/USB time to interfere with responsive STT.
            attempts = []
            v4l2 = getattr(cv2, "CAP_V4L2", None)
            if v4l2 is not None:
                attempts.append((candidate, v4l2))
            attempts.append((candidate, None))
            for source, backend in attempts:
                cap = cv2.VideoCapture(source, backend) if backend is not None else cv2.VideoCapture(source)
                if cap.isOpened():
                    try:
                        if hasattr(cv2, "VideoWriter_fourcc"):
                            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    except Exception:
                        pass
                    return cap
                last_error = f"Could not open camera {candidate!r}"
                try:
                    cap.release()
                except Exception:
                    pass
        raise RuntimeError(last_error or f"Could not open camera index {index}")

    def _capture_frame_locked(self):  # type: ignore[no-untyped-def]
        cap = self._open_capture_locked()
        try:
            frame = None
            # Discard stale frames after opening a USB camera, while retaining
            # the most recent successful read if a later read briefly fails.
            for _ in range(3):
                ok, candidate = cap.read()
                if ok and candidate is not None:
                    frame = candidate
                    time.sleep(0.02)
            if frame is None:
                raise RuntimeError("Camera returned no frame")
            return frame
        finally:
            cap.release()

    def capture_jpeg(self) -> bytes:
        with self._lock:
            if self._cv2 is not None:
                frame = self._capture_frame_locked()
                return self._encode_jpeg_locked(frame)
            return self._capture_with_fswebcam_locked()

    def _encode_jpeg_locked(self, frame) -> bytes:  # type: ignore[no-untyped-def]
        cv2 = self._cv2
        if cv2 is None:
            raise RuntimeError("OpenCV is not available")
        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), int(max(20, min(100, self.cfg.jpeg_quality)))],
        )
        if not ok:
            raise RuntimeError("Could not encode frame as JPEG")
        return encoded.tobytes()

    def probe(self) -> Dict[str, Any]:
        started = time.perf_counter()
        report: Dict[str, Any] = {
            "ok": False,
            "camera_device": str(self.cfg.camera_device),
            "camera_index": int(self.cfg.camera_index),
            "opencv_available": self.opencv_available,
            "face_detection_available": self.face_detection_available,
        }
        try:
            with self._lock:
                if self._cv2 is not None:
                    frame = self._capture_frame_locked()
                    height, width = frame.shape[:2]
                    encoded = self._encode_jpeg_locked(frame)
                    report.update({"width": int(width), "height": int(height), "jpeg_bytes": len(encoded)})
                else:
                    encoded = self._capture_with_fswebcam_locked()
                    report.update({"jpeg_bytes": len(encoded), "capture_backend": "fswebcam"})
            report["ok"] = True
        except Exception as exc:
            report["error"] = str(exc)
        report["latency_ms"] = round((time.perf_counter() - started) * 1000.0, 1)
        self._last_probe = dict(report)
        return report

    def capture_analysis_jpeg(
        self,
        *,
        motion_threshold: float = 0.035,
        detect_faces: bool = True,
        analysis_width: int = 320,
    ) -> Tuple[bytes, Dict[str, Any]]:
        """Capture one frame and return JPEG plus local motion/face evidence."""
        started = time.perf_counter()
        with self._lock:
            if self._cv2 is None:
                jpeg = self._capture_with_fswebcam_locked()
                return jpeg, {
                    "ok": True,
                    "opencv_available": False,
                    "face_detection_available": False,
                    "face_count": None,
                    "motion_detected": None,
                    "motion_score": None,
                    "note": "Snapshot available; install OpenCV for local face and motion awareness.",
                    "latency_ms": round((time.perf_counter() - started) * 1000.0, 1),
                }

            cv2 = self._cv2
            frame = self._capture_frame_locked()
            height, width = frame.shape[:2]
            target_w = max(160, min(640, int(analysis_width or 320)))
            scale = target_w / float(max(1, width))
            target_h = max(90, int(round(height * scale)))
            small = cv2.resize(frame, (target_w, target_h))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            try:
                gray = cv2.GaussianBlur(gray, (5, 5), 0)
            except Exception:
                pass

            motion_score: Optional[float] = None
            motion_detected: Optional[bool] = None
            if self._previous_gray is not None and getattr(self._previous_gray, "shape", None) == getattr(gray, "shape", None):
                diff = cv2.absdiff(gray, self._previous_gray)
                motion_score = float(diff.mean()) / 255.0
                motion_detected = motion_score >= max(0.001, min(0.5, float(motion_threshold)))
            self._previous_gray = gray.copy()

            face_count: Optional[int] = None
            boxes: list[list[int]] = []
            if detect_faces and self._face_cascade is not None:
                try:
                    faces = self._face_cascade.detectMultiScale(
                        gray,
                        scaleFactor=1.12,
                        minNeighbors=5,
                        minSize=(32, 32),
                    )
                    boxes = [[int(x), int(y), int(w), int(h)] for (x, y, w, h) in faces]
                    face_count = len(boxes)
                except Exception:
                    face_count = None

            jpeg = self._encode_jpeg_locked(frame)
            report = {
                "ok": True,
                "opencv_available": True,
                "face_detection_available": self.face_detection_available,
                "face_count": face_count,
                "face_boxes": boxes,
                "person_present": bool(face_count and face_count > 0),
                "motion_detected": motion_detected,
                "motion_score": round(motion_score, 4) if motion_score is not None else None,
                "motion_threshold": round(max(0.001, min(0.5, float(motion_threshold))), 4),
                "width": int(width),
                "height": int(height),
                "jpeg_bytes": len(jpeg),
                "latency_ms": round((time.perf_counter() - started) * 1000.0, 1),
            }
            return jpeg, report

    def _capture_with_fswebcam_locked(self) -> bytes:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            out_path = tmp.name
        try:
            cmd = [
                "fswebcam",
                "--no-banner",
                "--quiet",
                "--jpeg",
                str(int(max(20, min(100, self.cfg.jpeg_quality)))),
                "-d",
                self.cfg.camera_device,
                out_path,
            ]
            subprocess.check_call(cmd)
            data = Path(out_path).read_bytes()
            if len(data) < 500:
                raise RuntimeError("Camera snapshot was too small to be valid")
            return data
        except FileNotFoundError as exc:
            raise RuntimeError("fswebcam is not installed and OpenCV is not available.") from exc
        finally:
            try:
                os.remove(out_path)
            except OSError:
                pass
