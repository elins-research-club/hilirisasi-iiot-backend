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

    temp = get_num("temperature", "temp", "suhu", "bme688_temp")
    hum = get_num("humidity", "hum", "kelembapan", "bme688_hum")
    press = get_num("pressure", "press", "tekanan", "tekanan_udara", "barometer", "bme688_press")
    co2 = get_num("co2", "co2_ppm")
    co = get_num("co", "co_ppm", "carbon_monoxide")
    pm25 = get_num("pm25", "pm2_5", "pm2.5", "pms7003t_pm25")
    pm10 = get_num("pm10", "pm_10", "pms7003t_pm10")
    h2s = get_num("h2s", "h2s_ppm", "hydrogen_sulfide")
    ch4 = get_num("ch4", "metana", "gas_metana", "methane", "ch4_ppm", "methane_ppm")
    lpg = get_num("lpg", "gas_lpg", "lpg_ppm")
    current = get_num("current_ma", "current", "arus", "current_mA", "ina226_current")

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
        "pressure": press,
        "co2": co2,
        "co": co,
        "pm25": pm25,
        "pm10": pm10,
        "h2s": h2s,
        "ch4": ch4,
        "lpg": lpg,
        "current_ma": current,
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
