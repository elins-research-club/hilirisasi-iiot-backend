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
MQTT_TOPIC_PATTERN = "/iiot/+"
HARDWARE_GATEWAY_ID = os.getenv("HARDWARE_GATEWAY_ID", "IIOT-GATEWAY")
HARDWARE_NODE_ID = os.getenv("HARDWARE_NODE_ID", "e02d6ee6c5f39cfd")


def normalize_hardware_payload(data: dict) -> dict:
    """Map the real ChirpStack-to-EMQX envelope to the dashboard shape."""
    sensor = data.get("data") or {}
    return {
        "type": "environmental",
        "gateway_id": HARDWARE_GATEWAY_ID,
        "node_id": HARDWARE_NODE_ID,
        "source_dev_eui": data.get("dev_eui"),
        "event_id": f"{data.get('dev_eui')}-{data.get('f_cnt')}",
        "sequence": data.get("f_cnt"),
        "timestamp": data.get("received_at") or dt.datetime.now(dt.timezone.utc).isoformat(),
        "temperature": sensor.get("temperature"),
        "humidity": sensor.get("humidity"),
        "current_ma": sensor.get("current_ma"),
        "pressure": None,
        "bme_gas": None,
        "pm25": None,
        "pm10": None,
        "co": None,
        "no2": None,
        "so2": None,
        "o3": None,
        "co2": None,
        "pm1": None,
        "battery_voltage": None,
        "power_mw": None,
        "source": data.get("source"),
    }


def on_connect(client, userdata, flags, rc, properties=None):
    print(f"[OK] Connected to MQTT broker (rc={rc})")
    client.subscribe(MQTT_TOPIC_PATTERN)
    print(f"[WIFI] Subscribed to: {MQTT_TOPIC_PATTERN}")


def on_message(client, userdata, msg):
    manager, loop = userdata
    payload_str = msg.payload.decode()

    # Parse topic: /iiot/{dev_eui}
    parts = msg.topic.split("/")
    if len(parts) != 3 or parts[1] != "iiot" or not parts[2]:
        print(f"[WARN] Unexpected topic format: {msg.topic}")
        return

    dev_eui = parts[2]

    try:
        data = json.loads(payload_str)
        if data.get("dev_eui", dev_eui).lower() != dev_eui.lower():
            print("[WARN] Topic DevEUI berbeda dengan payload DevEUI")
            return
        normalized_data = normalize_hardware_payload(data)
        gateway_id = normalized_data["gateway_id"]
        node_id = normalized_data["node_id"]

        # db = SessionLocal()
        # try:
        #     if data_type == "environmental":
        #         crud.save_env_sensor_data(db, gateway_id, node_id, data)
        #     elif data_type == "ai_vision":
        #         crud.save_vision_snapshot(db, gateway_id, node_id, data)
        #     else:
        #         print(f"[WARN] Unknown data type: {data_type}")
        #         return
        # finally:
        #     db.close()

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
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, userdata=(manager, loop))
        else:
            client = mqtt.Client(userdata=(manager, loop))
    except AttributeError:
        client = mqtt.Client(userdata=(manager, loop))
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
