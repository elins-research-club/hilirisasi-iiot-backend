import paho.mqtt.client as mqtt
import json
import datetime as dt
from database import SessionLocal
import crud
import asyncio

import os
from dotenv import load_dotenv

load_dotenv()

MQTT_BROKER = os.getenv("MQTT_BROKER", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "backend-client-mqtt")
MQTT_TOPIC_PATTERN = "/iiot/+"
HARDWARE_GATEWAY_ID = os.getenv("HARDWARE_GATEWAY_ID", "IIOT-GATEWAY")
HARDWARE_NODE_ID = os.getenv("HARDWARE_NODE_ID", "e02d6ee6c5f39cfd")


def normalize_hardware_payload(data: dict, topic_dev_eui: str = "") -> dict:
    """Map any ChirpStack or raw hardware MQTT envelope to the dashboard shape."""
    if isinstance(data.get("data"), dict):
        sensor = data.get("data")
    elif isinstance(data.get("val"), dict):
        sensor = data.get("val")
    else:
        sensor = data
    raw_dev_eui = data.get("dev_eui") or data.get("node_id") or data.get("device_name") or topic_dev_eui or HARDWARE_NODE_ID
    
    # Normalize node_id aliases (node2, node-2, node_2 -> e02d6ee6c5f39cfd)
    if str(raw_dev_eui).lower() in ("node2", "node-2", "node_2", HARDWARE_NODE_ID.lower()):
        node_id = HARDWARE_NODE_ID
    else:
        node_id = str(raw_dev_eui)

    # Helper function for safe float parsing
    def get_num(*keys):
        for k in keys:
            v = sensor.get(k)
            if v is not None:
                try:
                    return float(v)
                except (ValueError, TypeError):
                    continue
        return None

    temp = get_num("temperature", "temp", "suhu")
    hum = get_num("humidity", "hum", "kelembapan")
    current = get_num("current_ma", "current", "arus", "current_mA")
    press = get_num("pressure", "press", "tekanan", "barometer")
    bme_gas = get_num("bme_gas", "gas_resistance", "gas", "gas_bme")
    pm25 = get_num("pm25", "pm2_5", "pm2.5")
    pm10 = get_num("pm10", "pm_10")
    pm1 = get_num("pm1", "pm1_0", "pm1.0")
    co = get_num("co", "co_ppm", "carbon_monoxide")
    no2 = get_num("no2", "no2_ppm")
    so2 = get_num("so2", "so2_ppm")
    o3 = get_num("o3", "o3_ppm", "ozone")
    co2 = get_num("co2", "co2_ppm")
    batt = get_num("battery_voltage", "voltage", "battery", "batt", "tegangan")
    power = get_num("power_mw", "power", "daya", "power_mW")

    # If power is not supplied but voltage (V) and current (mA) are present: P = V * I (mW)
    if power is None and batt is not None and current is not None:
        power = round(batt * current, 2)

    return {
        "type": "environmental",
        "gateway_id": data.get("gateway_id") or HARDWARE_GATEWAY_ID,
        "node_id": node_id,
        "source_dev_eui": raw_dev_eui,
        "event_id": f"{raw_dev_eui}-{data.get('f_cnt', 0)}",
        "sequence": data.get("f_cnt"),
        "timestamp": data.get("received_at") or data.get("timestamp") or dt.datetime.now(dt.timezone.utc).isoformat(),
        "temperature": temp,
        "humidity": hum,
        "current_ma": current,
        "pressure": press,
        "bme_gas": bme_gas,
        "pm25": pm25,
        "pm10": pm10,
        "co": co,
        "no2": no2,
        "so2": so2,
        "o3": o3,
        "co2": co2,
        "pm1": pm1,
        "battery_voltage": batt,
        "power_mw": power,
        "source": data.get("source"),
    }


def on_connect(client, userdata, flags, rc, properties=None):
    print(f"[OK] Connected to MQTT broker (rc={rc})")
    client.subscribe([("/iiot/+", 1), ("iiot/+", 1), ("/iiot/#", 1), ("iiot/#", 1)])
    print("[WIFI] Subscribed to IIoT topics (/iiot/+, iiot/+, /iiot/#, iiot/#)")


def on_message(client, userdata, msg):
    manager, loop = userdata
    payload_str = msg.payload.decode(errors="replace")

    parts = [p for p in msg.topic.split("/") if p]
    topic_dev_eui = parts[-1] if parts else HARDWARE_NODE_ID

    print(f"[MQTT RECV] topic={msg.topic} payload={payload_str[:200]}")

    try:
        data = json.loads(payload_str)
        normalized_data = normalize_hardware_payload(data, topic_dev_eui)
        gateway_id = normalized_data["gateway_id"]
        node_id = normalized_data["node_id"]

        print(f"[MQTT BROADCAST] gw={gateway_id} node={node_id} T={normalized_data['temperature']} H={normalized_data['humidity']} I={normalized_data['current_ma']} P={normalized_data['pressure']} PM25={normalized_data['pm25']}")

        # Broadcast update to WebSocket clients
        if manager and loop:
            asyncio.run_coroutine_threadsafe(
                manager.broadcast_gateway_update(gateway_id, node_id, normalized_data), loop
            )

    except Exception as e:
        print(f"[ERROR] Error processing MQTT message: {e}")
        import traceback
        traceback.print_exc()


def start_mqtt_client(manager=None):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    try:
        if hasattr(mqtt, 'CallbackAPIVersion'):
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID, userdata=(manager, loop))
        else:
            client = mqtt.Client(client_id=MQTT_CLIENT_ID, userdata=(manager, loop))
    except AttributeError:
        client = mqtt.Client(client_id=MQTT_CLIENT_ID, userdata=(manager, loop))
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        print(f"Connecting to MQTT Broker {MQTT_BROKER}:{MQTT_PORT}...")
        client.connect(MQTT_BROKER, MQTT_PORT, 2)
        client.loop_start()
    except Exception as e:
        print(f"[WARN] Failed to connect to MQTT broker: {e}. Running in HTTP-only mode.")
        return None
    return client
