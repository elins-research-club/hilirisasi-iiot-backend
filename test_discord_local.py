"""Test Script Notifikasi Discord (Mode Lokal / Mock)
Jalankan script ini untuk menguji pipeline notifikasi tanpa memerlukan koneksi webhook Discord asli.
Command: python test_discord_local.py
"""

import asyncio
import json
from discord_notifier import notify_from_alertmanager, get_mock_history

async def run_test():
    print("============================================================")
    print("🚀 MEMULAI SIMULASI NOTIFIKASI DISCORD (LOCAL MOCK MODE)")
    print("============================================================")
    
    # 1. Simulasi Alert Firing (Critical)
    sample_alert_critical = {
        "status": "firing",
        "labels": {
            "alertname": "HighGasConcentrationCritical",
            "gateway_id": "IIOT-GATEWAY-01",
            "node_id": "e02d6ee6c5f39cfd",
            "severity": "critical"
        },
        "annotations": {
            "summary": "Gas BME Resistance Terlalu Rendah (Bahaya Gas Terdeteksi)",
            "description": "Sensor BME680 membaca resistansi 12.4 kOhm (di bawah batas aman 20 kOhm) selama lebih dari 30 detik."
        }
    }
    
    print("\n[STEP 1] Mengirim Alert FIRING (Severity: CRITICAL)...")
    result1 = await notify_from_alertmanager(sample_alert_critical)
    print(f"Status Pengiriman: {result1.get('status')}")

    # 2. Simulasi Alert Warning
    sample_alert_warning = {
        "status": "firing",
        "labels": {
            "alertname": "HighCrowdDensityWarning",
            "gateway_id": "IIOT-GATEWAY-01",
            "node_id": "CAM-IKEA-JKT-001",
            "severity": "warning"
        },
        "annotations": {
            "summary": "Peringatan Kepadatan Kerumunan (Crowd Density)",
            "description": "Kamera mendeteksi kepadatan 0.18 orang/m² (mendekati threshold alert 0.20)."
        }
    }
    
    print("\n[STEP 2] Mengirim Alert FIRING (Severity: WARNING)...")
    result2 = await notify_from_alertmanager(sample_alert_warning)
    print(f"Status Pengiriman: {result2.get('status')}")

    # 3. Cek Riwayat Mock
    print("\n[STEP 3] Membaca Riwayat Notifikasi Mock Lokal...")
    history = get_mock_history()
    print(f"Total notifikasi tersimpan di mock_discord_alerts.json: {len(history)} pesan.")
    print("✅ Semua simulasi lokal berhasil dijalankan dengan sukses!")

if __name__ == "__main__":
    asyncio.run(run_test())
