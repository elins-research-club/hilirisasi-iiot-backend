# SINERGI IIoT — Backend Ingestion Worker (Prototype)

## Tentang Proyek

Backend ini adalah **prototype awal** dari sistem **Industrial Internet of Things (IIoT)** untuk monitoring lingkungan secara real-time. Sistem ini dirancang untuk menerima data sensor dari perangkat IoT melalui protokol MQTT, dengan infrastruktur Redis (cache) dan TimescaleDB (time-series database) yang sudah siap.


---

## Arsitektur

```
 IoT Device (simulasi_device.py)
        │
        ▼  MQTT (topik: iot/+/data, iot/+/status)
   ┌──────────┐
   │  EMQX    │  (MQTT Broker via Docker)
   └────┬─────┘
        │
        ▼  subscribe async
   ┌──────────────┐
   │ FastAPI       │
   │ mqtt_worker() │
   │ (print only)  │ ← Placeholder untuk Tahap 3 & 4
   └──────┬───────┘
          │
          ├── Redis        (terinisialisasi, belum dipakai)
          └── TimescaleDB  (container siap, belum connect)
```

---

## Status Pengembangan

Proyek ini masih dalam tahap awal pengembangan (proof-of-concept):

| Fitur | Status |
|-------|--------|
| MQTT Subscribe (EMQX) | ✅ Selesai |
| Redis inisialisasi | ✅ Selesai |
| Docker Compose (EMQX + Redis + TimescaleDB) | ✅ Selesai |
| Simulator device sederhana | ✅ Selesai |
| Parsing & validasi data MQTT | ❌ Belum |
| Simpan data ke TimescaleDB | ❌ Belum |
| REST API endpoints | ❌ Belum (hanya 1 health check) |
| WebSocket real-time | ❌ Belum |


---

## Komponen Utama

| File | Fungsi |
|------|--------|
| `main.py` | FastAPI app + background worker MQTT (async aiomqtt) — worker hanya mencetak payload yang diterima |
| `simulasi_device.py` | Simulator sederhana pengirim data sensor via MQTT tiap 3 detik |
| `docker-compose.yml` | Infrastruktur 3 service: EMQX (MQTT broker), Redis (cache), TimescaleDB (time-series database) |

### Detail File

#### `main.py`
- **MQTT**: Subscribe ke topik `iot/+/data` dan `iot/+/status` menggunakan library `aiomqtt`
- **Database**: Redis client sudah diinisialisasi (`redis.Redis(...)`) tapi belum digunakan
- **Catatan**: Di baris 36–40 terdapat placeholder komentar untuk implementasi Tahap 3 (parsing data, simpan ke DB) dan Tahap 4 (Redis PUBLISH notifikasi)
- **Endpoint**: Hanya `GET /` untuk health check

#### `simulasi_device.py`
- Mengirim data sensor sederhana (temperature, humidity, counter) ke topik `iot/device_macbook/data`
- Interval pengiriman: 3 detik
- Data: `device_id`, `temperature` (naik 0.1°C per iterasi), `humidity` (55 konstan), `counter`

#### `docker-compose.yml`
- **EMQX** — port `1883` (MQTT) & `18083` (Dashboard)
- **Redis 7** — port `6379`
- **TimescaleDB (PostgreSQL 14)** — port `5432`, user `myuser`, database `iot_data`

---

## Cara Menjalankan

### 1. Jalankan Infrastructure (Docker)

```bash
docker-compose up -d
```

### 2. Setup Virtual Environment & Install Dependencies

Gunakan **virtual environment (venv)** agar dependencies terisolasi dari global Python — ini memastikan versi library yang terinstall konsisten di semua mesin (reliable), dan jika tidak dipakai lagi tinggal hapus folder `venv/` tanpa meninggalkan residu (maintainable).

```bash
# Buat virtual environment
python -m venv venv

# Aktifkan (Windows PowerShell)
venv\Scripts\Activate.ps1
# Atau (Windows CMD)
venv\Scripts\activate

# Install dependencies dari requirements.txt
pip install -r requirements.txt

# Keluar dari venv setelah selesai bekerja
deactivate
```

### 3. Jalankan FastAPI (Terminal 1)

```bash
python -m uvicorn main:app --reload --port 8000
```

### 4. Jalankan Simulator (Terminal 2)

```bash
python simulasi_device.py
```

---

## Catatan Pengembangan

- **`main.py`** memiliki placeholder di `mqtt_worker()` untuk implementasi selanjutnya: parsing data, simpan ke TimescaleDB, update Redis cache, dan trigger Redis PUBLISH untuk notifikasi real-time.
- **`simulasi_device.py`** adalah simulator paling sederhana — hanya mengirim 3 parameter data. Ini bisa dikembangkan untuk mensimulasikan data lingkungan yang lebih kompleks (PM2.5, CO, dll) dan AI Vision.

---

*Backend SINERGI IIoT — Research Project*