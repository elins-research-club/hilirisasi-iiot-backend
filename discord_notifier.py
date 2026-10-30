"""Discord Notifier Service for SINERGI IIOT

Mendukung dua mode:
1. Production Mode: Mengirim notifikasi via Discord Webhook HTTPS POST.
2. Local/Mock Mode: Jika DISCORD_WEBHOOK_URL kosong atau tidak terjangkau,
   alert akan dicatat dalam format visual di console log dan disimpan
   ke dalam riwayat lokal (mock history) untuk keperluan testing & laporan progress.
"""

import os
import json
import asyncio
import datetime as dt
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
MOCK_HISTORY_FILE = ROOT / "mock_discord_alerts.json"

# In-memory alert history for quick inspection
_mock_alert_history: List[Dict[str, Any]] = []

# Anti-spam cooldown (alert_key -> last_sent_timestamp)
_last_sent_cache: Dict[str, float] = {}
COOLDOWN_SECONDS = 60.0  # Minimal jeda pengiriman untuk alert yang sama


def get_discord_webhook_url() -> str:
    return os.getenv("DISCORD_WEBHOOK_URL", "").strip()


def is_mock_mode() -> bool:
    url = get_discord_webhook_url()
    return not url or url.lower() in ("mock", "local", "none", "")


def _save_to_mock_history(record: Dict[str, Any]):
    """Simpan payload ke riwayat mock lokal."""
    global _mock_alert_history
    _mock_alert_history.insert(0, record)
    _mock_alert_history = _mock_alert_history[:100]  # Maksimal 100 entri
    try:
        MOCK_HISTORY_FILE.write_text(
            json.dumps(_mock_alert_history, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception as e:
        print(f"[DISCORD NOTIFIER] Gagal menyimpan mock history: {e}")


def get_mock_history() -> List[Dict[str, Any]]:
    """Ambil riwayat notifikasi mock."""
    global _mock_alert_history
    if not _mock_alert_history and MOCK_HISTORY_FILE.exists():
        try:
            _mock_alert_history = json.loads(MOCK_HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            _mock_alert_history = []
    return _mock_alert_history


def build_discord_embed(
    title: str,
    description: str,
    severity: str = "critical",
    status: str = "firing",
    fields: Optional[List[Dict[str, Any]]] = None,
    dashboard_url: Optional[str] = None
) -> Dict[str, Any]:
    """Bangun payload JSON Discord Embed sesuai standar Discord Webhook API."""
    # Color palette
    if status.lower() == "resolved":
        color = 0x57F287  # Hijau (Resolved)
        status_badge = "🟢 RESOLVED"
    elif severity.lower() == "warning":
        color = 0xFEE75C  # Kuning / Oranye (Warning)
        status_badge = "🟡 WARNING"
    else:
        color = 0xED4245  # Merah (Critical)
        status_badge = "🔴 CRITICAL"

    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    embed: Dict[str, Any] = {
        "title": f"{status_badge} • {title}",
        "description": description,
        "color": color,
        "timestamp": now_iso,
        "footer": {
            "text": "SINERGI IIOT Alert System",
            "icon_url": "https://img.icons8.com/fluency/48/industrial.png"
        }
    }

    if dashboard_url:
        embed["url"] = dashboard_url

    if fields:
        embed["fields"] = fields

    payload = {
        "username": "SINERGI IIOT Bot",
        "avatar_url": "https://img.icons8.com/fluency/96/sensor.png",
        "embeds": [embed]
    }
    return payload


def _print_local_mock_card(payload: Dict[str, Any]):
    """Cetak visualisasi kartu embed Discord di terminal lokal."""
    embed = payload.get("embeds", [{}])[0]
    title = embed.get("title", "No Title")
    desc = embed.get("description", "")
    fields = embed.get("fields", [])
    timestamp = embed.get("timestamp", "")

    border = "═" * 60
    print("\n" + border)
    print("📢 [DISCORD NOTIFICATION - LOCAL MOCK MODE]")
    print(border)
    print(f"Judul       : {title}")
    print(f"Deskripsi   : {desc}")
    print(f"Waktu (UTC) : {timestamp}")
    if fields:
        print("-" * 60)
        for f in fields:
            name = f.get("name", "")
            val = f.get("value", "")
            print(f" • {name:<16}: {val}")
    print(border)
    print("ℹ️ Mode: LOKAL (Set DISCORD_WEBHOOK_URL di .env untuk mengirim ke server Discord)")
    print(border + "\n")


def _send_http_sync(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Kirim HTTPS POST ke Discord secara synchronous (dijalankan di worker thread)."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Sinergi-IIoT-Notifier/1.0"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            return {"status": "success", "code": resp.status}
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="replace")
        return {"status": "error", "code": e.code, "detail": err_msg}
    except Exception as e:
        return {"status": "error", "code": 500, "detail": str(e)}


async def send_discord_notification(
    title: str,
    description: str,
    severity: str = "critical",
    status: str = "firing",
    fields: Optional[List[Dict[str, Any]]] = None,
    dashboard_url: Optional[str] = None,
    dedup_key: Optional[str] = None
) -> Dict[str, Any]:
    """Fungsi utama untuk mengirim notifikasi Discord (Async & Non-blocking)."""
    # 1. Cek Anti-Spam / Cooldown jika ada dedup_key
    now = dt.datetime.now().timestamp()
    if dedup_key:
        last_sent = _last_sent_cache.get(dedup_key, 0.0)
        if now - last_sent < COOLDOWN_SECONDS and status.lower() == "firing":
            remaining = int(COOLDOWN_SECONDS - (now - last_sent))
            print(f"[DISCORD NOTIFIER] Cooldown aktif untuk '{dedup_key}' ({remaining}s tersisa). Dilewati.")
            return {"status": "skipped", "reason": f"Cooldown active ({remaining}s remaining)"}
        _last_sent_cache[dedup_key] = now

    payload = build_discord_embed(
        title=title,
        description=description,
        severity=severity,
        status=status,
        fields=fields,
        dashboard_url=dashboard_url
    )

    webhook_url = get_discord_webhook_url()

    # 2. Jika mode MOCK / LOKAL
    if is_mock_mode():
        _print_local_mock_card(payload)
        record = {
            "id": f"mock-{int(now * 1000)}",
            "created_at": dt.datetime.now().isoformat(),
            "mode": "mock",
            "title": title,
            "severity": severity,
            "status": status,
            "payload": payload
        }
        _save_to_mock_history(record)
        return {"status": "mock_delivered", "record": record}

    # 3. Jika mode PRODUCTION (Webhook URL terisi)
    try:
        result = await asyncio.to_thread(_send_http_sync, webhook_url, payload)
        if result.get("status") == "success":
            print(f"[DISCORD NOTIFIER] Sukses terkirim ke Discord Webhook (HTTP {result.get('code')})")
        else:
            print(f"[DISCORD NOTIFIER] Gagal kirim ke Discord: {result}")
        return result
    except Exception as e:
        print(f"[DISCORD NOTIFIER] Exception saat kirim webhook: {e}")
        return {"status": "error", "detail": str(e)}


async def notify_from_alertmanager(alert: Dict[str, Any]) -> Dict[str, Any]:
    """Helper untuk memproses alert dari Prometheus Alertmanager payload."""
    status = alert.get("status", "firing")
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})

    alert_name = labels.get("alertname", "System Alert")
    severity = labels.get("severity", "critical")
    gateway_id = labels.get("gateway_id", "Unknown")
    node_id = labels.get("node_id", "Unknown")

    summary = annotations.get("summary", alert_name)
    description = annotations.get("description", "Peringatan parameter IIoT terpicu.")

    fields = [
        {"name": "Gateway", "value": f"`{gateway_id}`", "inline": True},
        {"name": "Node ID", "value": f"`{node_id}`", "inline": True},
        {"name": "Severity", "value": severity.upper(), "inline": True},
        {"name": "Detail", "value": description, "inline": False},
    ]

    dedup_key = f"{alert_name}:{gateway_id}:{node_id}:{status}"
    
    return await send_discord_notification(
        title=summary,
        description=description,
        severity=severity,
        status=status,
        fields=fields,
        dedup_key=dedup_key
    )


# CLI Direct Test
if __name__ == "__main__":
    print("[TEST] Menjalankan test notifikasi Discord secara lokal...")
    sample_alert = {
        "status": "firing",
        "labels": {
            "alertname": "HighTemperatureCritical",
            "gateway_id": "IIOT-GATEWAY",
            "node_id": "e02d6ee6c5f39cfd",
            "severity": "critical"
        },
        "annotations": {
            "summary": "High Temperature on IIOT-GATEWAY",
            "description": "Node e02d6ee6c5f39cfd reported temperature 48.5 °C for more than 30 seconds."
        }
    }
    res = asyncio.run(notify_from_alertmanager(sample_alert))
    print(f"[RESULT] {res}")
