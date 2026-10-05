# Deployment SINERGI IIOT

Panduan singkat untuk menjalankan backend, frontend, simulator, dan service observability.

## Arsitektur runtime

- Backend FastAPI: lokal atau container, port `8000`
- Frontend Next.js: lokal atau container, port `3000`
- Simulator: lokal atau container
- EMQX: Docker, MQTT `1883`, dashboard `18083`
- Telegraf: Docker, exporter Prometheus `9273`
- Prometheus: Docker, UI `9090`
- Alertmanager: Docker, UI `9093`
- PostgreSQL hanya menyimpan metadata aplikasi; telemetri tidak disimpan di PostgreSQL.

## Prasyarat

- Docker Desktop dan Docker Compose
- Python 3.11+
- Node.js dan npm
- Git

## Konfigurasi environment

Salin file environment contoh jika tersedia. Nilai minimum backend lokal:

```env
DATABASE_URL=postgresql://postgres:123@localhost:5433/iiot_db
MQTT_BROKER=127.0.0.1
MQTT_PORT=1883
PROMETHEUS_URL=http://localhost:9090
HARDWARE_GATEWAY_ID=IIOT-GATEWAY
HARDWARE_NODE_ID=e02d6ee6c5f39cfd
```

Jangan commit file `.env`, token, password broker, atau secret JWT.

## Menjalankan service Docker

Dari folder root project:

```powershell
docker compose up -d db emqx telegraf prometheus alertmanager
docker compose ps
```

Pastikan container berikut aktif:

```text
iiot_db
iiot_emqx
iiot_telegraf
iiot_prometheus
iiot_alertmanager
```

## Menjalankan backend lokal

```powershell
cd fastapi_iiot
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Dokumentasi API tersedia di `http://localhost:8000/docs`.

## Menjalankan frontend lokal

```powershell
cd nextjs_iiot
npm install
npm run dev
```

Buka `http://localhost:3000`.

## Menjalankan simulator

```powershell
cd fastapi_iiot
python simulator.py --interval 10
```

Simulator mengirim payload hardware ke:

```text
/iiot/e02d6ee6c5f39cfd
```

Payload saat ini hanya memiliki temperatur, kelembapan, dan arus. Parameter lain tetap `null` sampai hardware mengirimkannya.

## Verifikasi alur data

1. Cek EMQX pada `http://localhost:18083`.
2. Cek exporter Telegraf pada `http://localhost:9273/metrics`.
3. Buka Prometheus pada `http://localhost:9090`.
4. Jalankan query:

```promql
iiot_temperature{node_id="e02d6ee6c5f39cfd"}
iiot_humidity{node_id="e02d6ee6c5f39cfd"}
iiot_current_ma{node_id="e02d6ee6c5f39cfd"}
```

5. Login dashboard menggunakan akun aplikasi yang sudah dibuat oleh administrator.

Alur realtime:

```text
Simulator/Hardware → EMQX → Backend MQTT → WebSocket → Frontend
```

Alur histori:

```text
Hardware → EMQX → Telegraf → Prometheus → Backend query → Frontend
```

## Payload hardware

Forwarder ChirpStack saat ini mengirim envelope berikut:

```json
{
  "source": "chirpstack",
  "dev_eui": "e02d6ee6c5f39cfd",
  "device_name": "node-2",
  "f_cnt": 1,
  "f_port": 1,
  "data": {
    "packet_id": 1,
    "temperature": 29.1,
    "humidity": 64.1,
    "current_ma": 75.89
  }
}
```

Backend melakukan normalisasi payload tersebut untuk kebutuhan dashboard tanpa mengubah payload asli hardware.

## Troubleshooting singkat

- Status offline: pastikan hanya satu backend aktif dan port `8000` tidak dipakai container lain.
- MQTT tidak masuk: pastikan EMQX aktif di port `1883` dan backend subscribe ke `/iiot/+`.
- Histori kosong: cek metric `iiot_temperature` di Prometheus dan status Telegraf.
- Parameter `--`: parameter tersebut belum dikirim hardware, bukan error frontend.
- Perubahan frontend tidak terlihat: gunakan `Ctrl + Shift + R` atau restart `npm run dev`.
