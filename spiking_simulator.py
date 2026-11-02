"""Spiking Simulator untuk IIoT & Prometheus Alertmanager

Mensimulasikan data sensor IoT dengan lonjakan (spiking) ekstrem setiap 5 detik:
1. Dikirim ke topik Telegraf: 'sinergi/iiot/IIOT-GATEWAY-01/e02d6ee6c5f39cfd'
2. Dikirim ke topik Backend: '/iiot/e02d6ee6c5f39cfd'

Pipeline:
Simulator (Spike tiap 5s) -> EMQX (1883) -> Telegraf (9273) -> Prometheus (9090) 
-> Alertmanager (9093) -> FastAPI (/webhook/alert) -> Discord Webhook
"""

import os
import sys
import time
import json
import random
import datetime as dt
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

MQTT_BROKER = os.getenv("MQTT_BROKER", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
GATEWAY_ID = os.getenv("HARDWARE_GATEWAY_ID", "IIOT-GATEWAY-01")
NODE_ID = os.getenv("HARDWARE_NODE_ID", "e02d6ee6c5f39cfd")

# Topics
TELEGRAF_TOPIC = f"sinergi/iiot/{GATEWAY_ID}/{NODE_ID}"
BACKEND_TOPIC = f"/iiot/{NODE_ID}"

INTERVAL = 5.0  # Spike setiap 5 detik


def get_spiked_metrics(cycle: int) -> dict:
    """Menghasilkan metrik sensor dengan lonjakan suhu ekstrem (> 37°C Critical)."""
    # Fluktuasi suhu kritis antara 39.5°C s/d 48.0°C (ambang batas Prometheus > 37°C)
    temp_spike = round(random.uniform(41.0, 47.5), 1)
    hum_spike = round(random.uniform(78.0, 89.0), 1)   # Warning > 75%
    co_spike = round(random.uniform(3600, 4200), 1)    # Critical > 3500 ppm
    pm25_spike = round(random.uniform(58.0, 75.0), 1)  # Warning > 55 µg/m³
    current_ma = round(random.uniform(110.0, 145.0), 2)

    return {
        "temperature": temp_spike,
        "humidity": hum_spike,
        "pressure": 1013.25,
        "co2": round(random.uniform(1100, 1600), 0),
        "co": co_spike,
        "pm25": pm25_spike,
        "pm10": round(pm25_spike * 1.6, 1),
        "h2s": round(random.uniform(8.0, 14.0), 1),
        "ch4": round(random.uniform(900, 1300), 0),
        "lpg": round(random.uniform(850, 1250), 0),
        "current_ma": current_ma,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat()
    }


def main():
    print("=" * 65)
    print("🚀 SINERGI IIOT SPIKING SIMULATOR (5-SECOND INTERVAL)")
    print("=" * 65)
    print(f"MQTT Broker      : {MQTT_BROKER}:{MQTT_PORT}")
    print(f"Telegraf Topic   : {TELEGRAF_TOPIC}")
    print(f"Backend Topic    : {BACKEND_TOPIC}")
    print(f"Spike Interval   : {INTERVAL} detik")
    print(f"Threshold Kritis : Suhu > 37°C (Prometheus rule: CriticalTemperature)")
    print("=" * 65)

    client = mqtt.Client(client_id="iiot-spiking-simulator")
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        print("✅ Terhubung ke EMQX Broker.")
    except Exception as e:
        print(f"❌ Gagal konek ke MQTT: {e}")
        sys.exit(1)

    cycle = 0
    try:
        while True:
            cycle += 1
            metrics = get_spiked_metrics(cycle)

            # 1. Payload untuk Telegraf (format langsung dibaca telegraf json parser)
            telegraf_payload = {
                "temperature": metrics["temperature"],
                "humidity": metrics["humidity"],
                "pressure": metrics["pressure"],
                "co2": metrics["co2"],
                "co": metrics["co"],
                "pm25": metrics["pm25"],
                "pm10": metrics["pm10"],
                "h2s": metrics["h2s"],
                "ch4": metrics["ch4"],
                "lpg": metrics["lpg"],
                "current_ma": metrics["current_ma"],
                "timestamp": metrics["timestamp"]
            }

            # 2. Payload untuk FastAPI Backend / WebSocket Dashboard
            backend_payload = {
                "source": "chirpstack",
                "dev_eui": NODE_ID,
                "device_name": "node-2",
                "gateway_id": GATEWAY_ID,
                "f_cnt": cycle,
                "timestamp": metrics["timestamp"],
                "data": {
                    "temperature": metrics["temperature"],
                    "humidity": metrics["humidity"],
                    "pressure": metrics["pressure"],
                    "co2": metrics["co2"],
                    "co": metrics["co"],
                    "pm25": metrics["pm25"],
                    "pm10": metrics["pm10"],
                    "h2s": metrics["h2s"],
                    "ch4": metrics["ch4"],
                    "lpg": metrics["lpg"],
                    "current_ma": metrics["current_ma"],
                }
            }

            # Publikasikan ke kedua topik
            client.publish(TELEGRAF_TOPIC, json.dumps(telegraf_payload), qos=1)
            client.publish(BACKEND_TOPIC, json.dumps(backend_payload), qos=1)

            print(f"[🔥 SPIKE #{cycle:03d} - {dt.datetime.now().strftime('%H:%M:%S')}] "
                  f"Suhu={metrics['temperature']}°C (KRITIS >37) | "
                  f"CO={metrics['co']}ppm | "
                  f"Hum={metrics['humidity']}%")

            time.sleep(INTERVAL)

    except KeyboardInterrupt:
        print("\n[STOP] Spiking simulator dihentikan.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
