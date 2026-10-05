import json
from functools import lru_cache
from pathlib import Path

@lru_cache
def get_thresholds():
    return json.loads((Path(__file__).parent / "config" / "thresholds.json").read_text(encoding="utf-8"))

def sensor_status(value, threshold, direction="high"):
    if value is None or threshold is None or threshold <= 0:
        return "unknown"
    if direction == "low":
        if value < threshold:
            return "danger"
        if value < threshold * 1.12:
            return "warning"
        return "good"
    if value > threshold:
        return "danger"
    if value > threshold * 0.8:
        return "warning"
    return "good"
