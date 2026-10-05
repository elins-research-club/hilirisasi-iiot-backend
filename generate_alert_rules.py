"""Generate Prometheus rules from config/thresholds.json.

Run from fastapi_iiot: python generate_alert_rules.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = Path(__file__).resolve().parent / "config" / "thresholds.json"
OUTPUT = ROOT / "prometheus" / "alert.rules.yml"


def alert_name(metric: str, level: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[^a-zA-Z0-9]+", metric)) + level


def main():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    lines = ["groups:", "- name: iiotsystem", "  rules:"]
    for metric, item in config.items():
        threshold = item.get("threshold")
        if threshold is None or metric in {"pressure", "battery_voltage"}:
            continue
        metric_name = f"iiot_{metric}"
        warning = threshold * 0.8
        for name, limit, severity in (("Warning", warning, "warning"), ("Critical", threshold, "critical")):
            lines.extend([
                f"  - alert: {alert_name(metric, name)}",
                f"    expr: {metric_name} > {limit:g}",
                "    for: 30s",
                "    labels:",
                f"      severity: {severity}",
                "    annotations:",
                f'      summary: "High {metric} on {{{{ $labels.gateway_id }}}}"',
                f'      description: "Node {{{{ $labels.node_id }}}} reported {metric} {{{{ $value }}}} for more than 30 seconds."',
                "",
            ])
    lines.extend([
        "  - alert: HighCrowdWarning",
        "    expr: iiot_person_count > 30",
        "    for: 30s",
        "    labels:",
        "      severity: critical",
        "    annotations:",
        '      summary: "High Crowd Density on {{ $labels.gateway_id }}"',
        '      description: "Camera {{ $labels.node_id }} detected {{ $value }} people for more than 30 seconds."',
    ])
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
