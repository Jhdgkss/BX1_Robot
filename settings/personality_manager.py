# ============================================================
# BX1 PERSONALITY SETTINGS MANAGER
# ============================================================

import json
from pathlib import Path

DEFAULT_NAME = "LEO"

DEFAULT_PERSONALITY = {
    "honesty": 95,
    "humour": 60,
    "sarcasm": 40,
    "confidence": 85,
    "curiosity": 90,
    "warmth": 60,
    "directness": 90,
    "independence": 85,
    "emotional_expression": 45,
    "formality": 15,
    "technical_depth": 85,
    "chattiness": 35,
}

DISPLAY_NAMES = {
    "honesty": "Honesty",
    "humour": "Humour",
    "sarcasm": "Sarcasm",
    "confidence": "Confidence",
    "curiosity": "Curiosity",
    "warmth": "Warmth",
    "directness": "Directness",
    "independence": "Independence",
    "emotional_expression": "Emotional expression",
    "formality": "Formality",
    "technical_depth": "Technical depth",
    "chattiness": "Chattiness",
}

ALIASES = {
    "humor": "humour",
    "emotional expression": "emotional_expression",
    "emotional-expression": "emotional_expression",
    "technical depth": "technical_depth",
    "technical-depth": "technical_depth",
}


class PersonalityManager:

    def __init__(self, file_path=None):
        self.file_path = (
            Path(file_path)
            if file_path is not None
            else Path(__file__).resolve().parent / "personality.json"
        )
        self.name = DEFAULT_NAME
        self.values = {}
        self.load()

    @staticmethod
    def _normalise_name(name: str) -> str:
        name = (name or "").strip().lower()
        if name in ALIASES:
            return ALIASES[name]
        name = name.replace("-", "_").replace(" ", "_")
        if name == "humor":
            return "humour"
        return name

    @staticmethod
    def _clean_robot_name(name) -> str:
        cleaned = " ".join(str(name or "").strip().split())
        if not cleaned:
            raise ValueError("Robot name cannot be blank.")
        if len(cleaned) > 40:
            raise ValueError("Robot name must be 40 characters or fewer.")
        return cleaned

    def load(self):
        values = dict(DEFAULT_PERSONALITY)
        robot_name = DEFAULT_NAME

        if self.file_path.exists():
            try:
                with self.file_path.open("r", encoding="utf-8") as handle:
                    loaded = json.load(handle)

                if isinstance(loaded, dict):
                    if "name" in loaded:
                        try:
                            robot_name = self._clean_robot_name(loaded.get("name"))
                        except ValueError:
                            robot_name = DEFAULT_NAME

                    for key, value in loaded.items():
                        normalised = self._normalise_name(key)
                        if normalised not in DEFAULT_PERSONALITY:
                            continue
                        if isinstance(value, bool):
                            continue
                        try:
                            numeric = int(round(float(value)))
                        except (TypeError, ValueError):
                            continue
                        values[normalised] = max(0, min(100, numeric))

            except Exception as error:
                print(f"[PERSONALITY] Could not read personality.json: {error}")
                print("[PERSONALITY] Using defaults.")

        self.name = robot_name
        self.values = values
        self.save()
        return self.get_all()

    def save(self):
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.file_path.with_suffix(".json.tmp")
        payload = {"name": self.name, **self.values}

        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")

        temporary.replace(self.file_path)

    def get_all(self):
        return {"name": self.name, **self.values}

    def get_name(self) -> str:
        return self.name

    def set_name(self, name: str):
        previous = self.name
        self.name = self._clean_robot_name(name)
        self.save()
        return {
            "setting": "name",
            "display_name": "Name",
            "previous": previous,
            "value": self.name,
            "file": str(self.file_path),
        }

    def get(self, setting: str):
        key = self._normalise_name(setting)
        if key == "name":
            return self.name
        if key not in self.values:
            raise KeyError(f"Unknown personality setting '{setting}'.")
        return self.values[key]

    def set(self, setting: str, value):
        key = self._normalise_name(setting)
        if key == "name":
            return self.set_name(value)
        if key not in DEFAULT_PERSONALITY:
            raise KeyError(f"Unknown personality setting '{setting}'.")
        if isinstance(value, bool):
            raise ValueError("Personality values must be percentages from 0 to 100.")
        try:
            numeric = int(round(float(value)))
        except (TypeError, ValueError) as error:
            raise ValueError(
                "Personality values must be percentages from 0 to 100."
            ) from error
        if not 0 <= numeric <= 100:
            raise ValueError("Personality values must be between 0 and 100.")
        previous = self.values[key]
        self.values[key] = numeric
        self.save()
        return {
            "setting": key,
            "display_name": DISPLAY_NAMES[key],
            "previous": previous,
            "value": numeric,
            "file": str(self.file_path),
        }

    def set_many(self, values: dict, *, name=None):
        new_values = dict(self.values)

        for setting, value in dict(values or {}).items():
            key = self._normalise_name(setting)
            if key not in DEFAULT_PERSONALITY:
                raise KeyError(f"Unknown personality setting '{setting}'.")
            if isinstance(value, bool):
                raise ValueError("Personality values must be percentages from 0 to 100.")
            try:
                numeric = int(round(float(value)))
            except (TypeError, ValueError) as error:
                raise ValueError(
                    "Personality values must be percentages from 0 to 100."
                ) from error
            if not 0 <= numeric <= 100:
                raise ValueError("Personality values must be between 0 and 100.")
            new_values[key] = numeric

        new_name = self.name if name is None else self._clean_robot_name(name)
        self.values = new_values
        self.name = new_name
        self.save()
        return self.get_all()

    def formatted_summary(self):
        lines = [f"Name: {self.name}"]
        lines.extend(
            f"{DISPLAY_NAMES[key]}: {self.values[key]}%"
            for key in DEFAULT_PERSONALITY
        )
        return "\n".join(lines)
