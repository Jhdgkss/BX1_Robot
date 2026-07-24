"""Optional BX1 perception helpers.

This module keeps YOLO/object-detection code out of main.py.  It is deliberately
optional: the app still runs if ultralytics/OpenCV are not installed.  When YOLO
is available it returns a small structured packet that can be fed into BX1's
chat/agent layer or sent back to the robot body.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


INSTALL_HINT = (
    "YOLO support is optional. Install it with:\n"
    "  python -m pip install ultralytics opencv-python\n\n"
    "Recommended first model for BX1: yolov8n.pt. It downloads automatically "
    "the first time Ultralytics uses it."
)


@dataclass
class DetectionPacket:
    ok: bool
    model: str
    detections: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    annotated_path: str = ""
    error: str = ""
    install_hint: str = INSTALL_HINT
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "model": self.model,
            "detections": self.detections,
            "summary": self.summary,
            "annotated_path": self.annotated_path,
            "error": self.error,
            "install_hint": self.install_hint,
            "created_at": self.created_at,
        }


class YoloDetector:
    """Lazy Ultralytics YOLO detector with no hard dependency at import time."""

    def __init__(self) -> None:
        self._model_name: str = ""
        self._model: Any = None
        self._load_error: str = ""

    @staticmethod
    def is_available() -> bool:
        try:
            import ultralytics  # noqa: F401
            return True
        except Exception:
            return False

    def status(self) -> Dict[str, Any]:
        return {
            "available": self.is_available(),
            "loaded_model": self._model_name,
            "last_error": self._load_error,
            "install_hint": INSTALL_HINT,
        }

    def _load(self, model_name: str) -> Any:
        model_name = (model_name or "yolov8n.pt").strip() or "yolov8n.pt"
        if self._model is not None and self._model_name == model_name:
            return self._model
        try:
            from ultralytics import YOLO
            self._model = YOLO(model_name)
            self._model_name = model_name
            self._load_error = ""
            return self._model
        except Exception as exc:
            self._model = None
            self._model_name = ""
            self._load_error = str(exc)
            raise

    def detect_image(
        self,
        image_path: str | Path,
        model_name: str = "yolov8n.pt",
        confidence: float = 0.35,
        max_det: int = 20,
        image_size: int = 640,
        draw_boxes: bool = True,
        output_dir: str | Path | None = None,
    ) -> Dict[str, Any]:
        path = Path(image_path)
        if not path.exists():
            return DetectionPacket(ok=False, model=model_name, error=f"Image does not exist: {path}").to_dict()
        if not self.is_available():
            return DetectionPacket(ok=False, model=model_name, error="Ultralytics YOLO is not installed.").to_dict()
        try:
            model = self._load(model_name)
            results = model.predict(
                source=str(path),
                conf=max(0.01, min(0.99, float(confidence))),
                max_det=max(1, min(200, int(max_det))),
                imgsz=max(160, min(1920, int(image_size))),
                verbose=False,
            )
            result = results[0] if results else None
            detections: List[Dict[str, Any]] = []
            if result is not None and getattr(result, "boxes", None) is not None:
                names = getattr(result, "names", {}) or {}
                for idx, box in enumerate(result.boxes):
                    cls_id = int(box.cls[0].item()) if getattr(box, "cls", None) is not None else -1
                    label = str(names.get(cls_id, cls_id))
                    conf = float(box.conf[0].item()) if getattr(box, "conf", None) is not None else 0.0
                    xyxy = [float(v) for v in box.xyxy[0].tolist()] if getattr(box, "xyxy", None) is not None else [0.0, 0.0, 0.0, 0.0]
                    detections.append({
                        "id": idx,
                        "label": label,
                        "confidence": round(conf, 4),
                        "box_xyxy": [round(v, 1) for v in xyxy],
                        "centre_xy": [round((xyxy[0] + xyxy[2]) / 2.0, 1), round((xyxy[1] + xyxy[3]) / 2.0, 1)],
                    })
            annotated_path = ""
            if draw_boxes and result is not None:
                annotated_path = self._save_annotated(result, path, output_dir)
            summary = summarize_detections(detections)
            return DetectionPacket(
                ok=True,
                model=model_name,
                detections=detections,
                summary=summary,
                annotated_path=annotated_path,
            ).to_dict()
        except Exception as exc:
            return DetectionPacket(ok=False, model=model_name, error=str(exc)).to_dict()

    def _save_annotated(self, result: Any, source_path: Path, output_dir: str | Path | None) -> str:
        try:
            from PIL import Image
            import numpy as np
            out_dir = Path(output_dir) if output_dir else source_path.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = out_dir / f"{source_path.stem}_yolo_{stamp}.jpg"
            arr = result.plot()  # Ultralytics returns a numpy image array.
            if isinstance(arr, np.ndarray):
                # result.plot() is BGR in most Ultralytics/OpenCV paths.
                if arr.ndim == 3 and arr.shape[2] >= 3:
                    arr = arr[:, :, :3][:, :, ::-1]
                Image.fromarray(arr).save(out_path, quality=92)
                return str(out_path)
        except Exception:
            return ""
        return ""


def summarize_detections(detections: List[Dict[str, Any]]) -> str:
    if not detections:
        return "No objects detected."
    counts = Counter(str(d.get("label", "object")) for d in detections)
    parts = [f"{count} {label}" for label, count in counts.most_common()]
    top = sorted(detections, key=lambda d: float(d.get("confidence", 0.0)), reverse=True)[:3]
    top_text = ", ".join(f"{d.get('label')} {float(d.get('confidence', 0.0)):.0%}" for d in top)
    return f"Detected {len(detections)} object(s): " + ", ".join(parts) + (f". Highest confidence: {top_text}." if top_text else ".")


def detections_to_prompt_context(packet: Dict[str, Any]) -> str:
    if not packet or not packet.get("ok"):
        return "YOLO object detection was not available or did not run."
    detections = packet.get("detections") or []
    if not detections:
        return "YOLO object detection ran and found no known objects."
    lines = ["YOLO OBJECT DETECTION CONTEXT:", str(packet.get("summary") or "")]
    for det in detections[:20]:
        lines.append(
            f"- {det.get('label')} confidence={float(det.get('confidence', 0.0)):.2f} "
            f"centre={det.get('centre_xy')} box={det.get('box_xyxy')}"
        )
    return "\n".join(lines)
