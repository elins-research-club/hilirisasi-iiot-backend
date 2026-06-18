import asyncio
import json
from fastapi import FastAPI
import aiomqtt
import redis
from contextlib import asynccontextmanager

# 1. Konfigurasi Koneksi (Sesuaikan dengan file YAML Anda)
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
REDIS_HOST = "localhost"
REDIS_PORT = 6379

# Inisialisasi Client Redis
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

# 2. Fungsi Background Worker (Mendengarkan MQTT)
async def mqtt_worker():
    print("Background Worker: Menghubungkan ke EMQX...")
    
    # Menghubungkan ke EMQX Broker
    async with aiomqtt.Client(hostname=MQTT_BROKER, port=MQTT_PORT) as client:
        # Subscribe ke topik wildcard sesuai jobdesk: iot/+/data dan iot/+/status
        await client.subscribe("iot/+/data")
        await client.subscribe("iot/+/status")
        print("Background Worker: Sukses Subscribe ke topik iot/+/data dan iot/+/status")

        # Loop terus-menerus untuk mendengarkan pesan masuk
        async for message in client.messages:
            topic = str(message.topic)
            payload_raw = message.payload.decode()
            
            print(f"\n[Pesan Baru] Topik: {topic}")
            print(f"[Payload Raw]: {payload_raw}")
            
            # PENTING: Di sinilah tempat untuk melakukan TAHAP 3 & 4 nanti:
            # - Parsing & Validasi Data (Tahap 3)
            # - Simpan ke TimescaleDB (Tahap 3)
            # - Update cache ke Redis SET (Tahap 3)
            # - Trigger Redis PUBLISH (Tahap 4)

# 3. Fitur Lifespan FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Logika saat FastAPI baru menyala: Jalankan worker MQTT di latar belakang
    worker_task = asyncio.create_task(mqtt_worker())
    yield
    # Logika saat FastAPI dimatikan: Batalkan task worker
    worker_task.cancel()

# 4. Inisialisasi Aplikasi FastAPI
app = FastAPI(lifespan=lifespan)

@app.get("/")
def home():
    return {"message": "FastAPI IoT Ingestion Worker berjalan aktif!"}