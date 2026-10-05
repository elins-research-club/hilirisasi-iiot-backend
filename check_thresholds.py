import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
config = json.loads((ROOT / "config" / "thresholds.json").read_text(encoding="utf-8"))

assert config, "threshold config kosong"
for sensor_id, item in config.items():
    assert isinstance(item["threshold"], (int, float)), sensor_id
    assert item["min"] < item["max"], sensor_id
    assert item["zones"], sensor_id
    assert item["zones"][-1][0] == item["max"], sensor_id

rules = (ROOT.parent / "prometheus" / "alert.rules.yml").read_text(encoding="utf-8")
for sensor_id, item in config.items():
    if sensor_id not in {"pressure", "battery_voltage"}:
        assert f"iiot_{sensor_id}" in rules, sensor_id

print(f"OK: {len(config)} sensor config dan rule Prometheus tervalidasi")
