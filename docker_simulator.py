"""SINERGI IIoT Full-Telemetry Docker Simulator (EMQX + Telegraf + Prometheus + FastAPI WebSocket)"""

import os
import sys
import time
import math
import json
import random
import datetime as dt
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

MQTT_BROKER = os.getenv("MQTT_BROKER", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
GATEWAY_ID = os.getenv("HARDWARE_GATEWAY_ID", "IIOT-GATEWAY")
NODE_ID = os.getenv("HARDWARE_NODE_ID", "e02d6ee6c5f39cfd")

TELEGRAF_TOPIC = f"sinergi/iiot/{GATEWAY_ID}/{NODE_ID}"
BACKEND_TOPIC = f"/iiot/{NODE_ID}"
INTERVAL = 3.0


def generate_metrics(cycle: int) -> dict:
    phase = cycle * 0.25
    temperature = round(30.4 + math.sin(phase) * 2.2 + random.uniform(-0.3, 0.3), 1)
    humidity = round(64.0 + math.cos(phase * 0.8) * 6.5 + random.uniform(-0.8, 0.8), 1)
    pressure = round(1008.6 + math.sin(phase * 0.3) * 1.4 + random.uniform(-0.2, 0.2), 1)
    bme_gas = round(142000 + math.cos(phase * 0.5) * 18000 + random.uniform(-2500, 2500), 0)

    pm1 = round(14.0 + abs(math.sin(phase * 0.6)) * 8.0 + random.uniform(-0.8, 0.8), 1)
    pm25 = round(23.5 + abs(math.sin(phase * 0.6)) * 18.0 + random.uniform(-1.2, 1.2), 1)
    pm10 = round(pm25 * 1.65 + random.uniform(2.0, 6.0), 1)

    co2 = round(612 + math.sin(phase * 0.7) * 95 + random.uniform(-12, 12), 0)
    co = round(1180 + abs(math.sin(phase * 0.4)) * 640 + random.uniform(-40, 40), 0)
    no2 = round(28.0 + abs(math.cos(phase * 0.5)) * 19.0 + random.uniform(-1.5, 1.5), 1)
    so2 = round(16.0 + abs(math.sin(phase * 0.35)) * 14.0 + random.uniform(-1.0, 1.0), 1)
    o3 = round(44.0 + abs(math.cos(phase * 0.45)) * 26.0 + random.uniform(-2.0, 2.0), 1)

    battery_voltage = round(3.92 + math.sin(phase * 0.1) * 0.08 + random.uniform(-0.01, 0.01), 2)
    current_ma = round(142.0 + math.sin(phase * 0.9) * 24.0 + random.uniform(-3.0, 3.0), 1)
    power_mw = round(battery_voltage * current_ma, 0)

    return {
        "temperature": temperature,
        "humidity": humidity,
        "pressure": pressure,
        "bme_gas": bme_gas,
        "pm1": pm1,
        "pm25": pm25,
        "pm10": pm10,
        "co2": co2,
        "co": co,
        "no2": no2,
        "so2": so2,
        "o3": o3,
        "battery_voltage": battery_voltage,
        "current_ma": current_ma,
        "power_mw": power_mw,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def main():
    print("=" * 65)
    print("SINERGI IIOT DOCKER TELEMETRY SIMULATOR")
    print("=" * 65)
    print(f"MQTT Broker    : {MQTT_BROKER}:{MQTT_PORT}")
    print(f"Telegraf Topic : {TELEGRAF_TOPIC}")
    print(f"Backend Topic  : {BACKEND_TOPIC}")
    print(f"Interval       : {INTERVAL}s")
    print("=" * 65)

    try:
        if hasattr(mqtt, "CallbackAPIVersion"):
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="sinergi-docker-simulator")
        else:
            client = mqtt.Client(client_id="sinergi-docker-simulator")
    except AttributeError:
        client = mqtt.Client(client_id="sinergi-docker-simulator")

    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()

    cycle = 0
    try:
        while True:
            cycle += 1
            m = generate_metrics(cycle)

            # 1. Publish to Telegraf -> Prometheus in Docker
            client.publish(TELEGRAF_TOPIC, json.dumps(m), qos=1)

            # 2. Publish to FastAPI MQTT Client -> WebSocket in Docker/Local
            backend_payload = {
                "source": "chirpstack",
                "dev_eui": NODE_ID,
                "device_name": "node-2",
                "gateway_id": GATEWAY_ID,
                "f_cnt": cycle,
                "timestamp": m["timestamp"],
                "data": m,
            }
            client.publish(BACKEND_TOPIC, json.dumps(backend_payload), qos=1)

            print(
                f"[SIM #{cycle:04d}] T={m['temperature']}C H={m['humidity']}% "
                f"PM2.5={m['pm25']} CO2={m['co2']}ppm V={m['battery_voltage']}V I={m['current_ma']}mA",
                flush=True,
            )
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print("\n[STOP] Simulator stopped.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
