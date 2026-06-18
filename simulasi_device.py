import time
import json
import paho.mqtt.client as mqtt

# Konfigurasi Broker Lokal
BROKER_HOST = "localhost"
BROKER_PORT = 1883
TOPIC = "iot/device_macbook/data"

client = mqtt.Client()

print("Menghubungkan ke EMQX Broker...")
client.connect(BROKER_HOST, BROKER_PORT, 60)

# Kirim data setiap 3 detik
try:
    count = 1
    while True:
        data_sensor = {
            "device_id": "macbook_01",
            "temperature": 24.0 + (count * 0.1),
            "humidity": 55,
            "counter": count
        }
        
        payload = json.dumps(data_sensor)
        client.publish(TOPIC, payload)
        print(f"[{count}] Terkirim ke {TOPIC}: {payload}")
        
        count += 1
        time.sleep(3)
except KeyboardInterrupt:
    print("\nSimulasi dihentikan.")
    client.disconnect()