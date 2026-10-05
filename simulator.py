"""Simulate the Raspberry Pi sensor_ai.v2 two-node MQTT contract."""

import argparse
import datetime as dt
import json
import os
import random
import time
from pathlib import Path

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

TARGET_DEV_EUI = os.getenv("TARGET_DEV_EUI", "e02d6ee6c5f39cfd")
DEVICE_NAME = os.getenv("DEVICE_NAME", "node-2")
MQTT_BROKER = os.getenv("MQTT_BROKER", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = f"/iiot/{TARGET_DEV_EUI}"
DEFAULT_INTERVAL = 10.0
STATE_FILE = Path(os.getenv("SIMULATOR_STATE_FILE", "state.json"))


def load_sequence() -> int:
    try:
        values = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return int(values.get(TARGET_DEV_EUI, 0))
    except (FileNotFoundError, ValueError, TypeError, json.JSONDecodeError):
        return 0


def save_sequence(sequence: int) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({TARGET_DEV_EUI: sequence}), encoding="utf-8")


def make_payload(sequence: int) -> dict:
    """Return the exact JSON envelope produced by chirpstack_to_emqx.py."""
    return {
        "source": "chirpstack",
        "dev_eui": TARGET_DEV_EUI,
        "device_name": DEVICE_NAME,
        "f_cnt": sequence,
        "f_port": 1,
        "data": {
            "packet_id": sequence % 256,
            "temperature": round(random.uniform(22.0, 38.0), 1),
            "humidity": round(random.uniform(40.0, 85.0), 1),
            "current_ma": round(random.uniform(65.0, 95.0), 2),
        },
    }


def publish_once(client: mqtt.Client | None, sequence: int, dry_run: bool) -> int:
    sequence += 1
    payload = make_payload(sequence)
    save_sequence(sequence)
    if not dry_run and client is not None:
        result = client.publish(MQTT_TOPIC, json.dumps(payload), qos=1, retain=False)
        result.wait_for_publish()
    print(f"published dev_eui={TARGET_DEV_EUI} f_cnt={sequence} data={payload['data']}")
    return sequence


def main() -> None:
    parser = argparse.ArgumentParser(description="sensor_ai.v2 two-node simulator")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sequence = load_sequence()
    client = None
    if not args.dry_run:
        client = mqtt.Client()
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()

    print(f"[SIM] {TARGET_DEV_EUI} -> {MQTT_BROKER}:{MQTT_PORT}")
    print(f"[SIM] Topic: {MQTT_TOPIC} | interval: {args.interval}s | dry-run: {args.dry_run}")
    try:
        while True:
            sequence = publish_once(client, sequence, args.dry_run)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[STOP] Simulator stopped.")
    finally:
        if client is not None:
            client.loop_stop()
            client.disconnect()


if __name__ == "__main__":
    main()
