from sqlalchemy.orm import Session
import models
import datetime
import math

# ── ISPU Indonesia Calculation ───────────────────────────────────
# Berdasarkan PP No. 41 Tahun 1999
# Sub-index dihitung per polutan, ISPU = max(semua sub-index)

# ISPU Breakpoints: (Clow, Chigh, Ilow, Ihigh)
ISPU_BREAKPOINTS_PM25 = [
    (0, 15.5, 0, 50),
    (15.6, 55.4, 51, 100),
    (55.5, 150.4, 101, 199),
    (150.5, 250.4, 200, 299),
    (250.5, 500, 300, 500),
]

ISPU_BREAKPOINTS_PM10 = [
    (0, 50, 0, 50),
    (51, 150, 51, 100),
    (151, 350, 101, 199),
    (351, 420, 200, 299),
    (421, 600, 300, 500),
]

ISPU_BREAKPOINTS_CO = [  # in μg/m³ (1 ppm ≈ 1145 μg/m³ for CO)
    (0, 4000, 0, 50),
    (4001, 8000, 51, 100),
    (8001, 15000, 101, 199),
    (15001, 30000, 200, 299),
    (30001, 60000, 300, 500),
]

ISPU_BREAKPOINTS_NO2 = [
    (0, 80, 0, 50),
    (81, 200, 51, 100),
    (201, 1130, 101, 199),
    (1131, 2260, 200, 299),
    (2261, 3000, 300, 500),
]

ISPU_BREAKPOINTS_SO2 = [
    (0, 52, 0, 50),
    (53, 180, 51, 100),
    (181, 400, 101, 199),
    (401, 800, 200, 299),
    (801, 1200, 300, 500),
]

ISPU_BREAKPOINTS_O3 = [
    (0, 120, 0, 50),
    (121, 235, 51, 100),
    (236, 400, 101, 199),
    (401, 800, 200, 299),
    (801, 1200, 300, 500),
]


def _calc_sub_index(concentration: float, breakpoints: list) -> int:
    """Calculate ISPU sub-index for a single pollutant."""
    for i, (c_low, c_high, i_low, i_high) in enumerate(breakpoints):
        if c_low <= concentration <= c_high:
            sub = ((i_high - i_low) / (c_high - c_low)) * (concentration - c_low) + i_low
            return round(sub)
        # Catch gaps between current breakpoint and next breakpoint
        if i < len(breakpoints) - 1:
            next_c_low = breakpoints[i+1][0]
            if c_high < concentration < next_c_low:
                sub = ((i_high - i_low) / (c_high - c_low)) * (concentration - c_low) + i_low
                return round(sub)
    # If above highest breakpoint, cap at 500
    return 500


def calculate_ispu(pm25=0, pm10=0, co=0, no2=0, so2=0, o3=0) -> int:
    """Calculate ISPU Indonesia (max of all sub-indices)."""
    sub_indices = [
        _calc_sub_index(pm25, ISPU_BREAKPOINTS_PM25),
        _calc_sub_index(pm10, ISPU_BREAKPOINTS_PM10),
        _calc_sub_index(co, ISPU_BREAKPOINTS_CO),
        _calc_sub_index(no2, ISPU_BREAKPOINTS_NO2),
        _calc_sub_index(so2, ISPU_BREAKPOINTS_SO2),
        _calc_sub_index(o3, ISPU_BREAKPOINTS_O3),
    ]
    return max(sub_indices) if sub_indices else 0


def get_ispu_level(ispu: int) -> dict:
    """Get ISPU category info based on ISPU value."""
    if ispu <= 50:
        return {"label": "Baik", "color": "#22c55e", "status": "baik"}
    if ispu <= 100:
        return {"label": "Sedang", "color": "#3b82f6", "status": "sedang"}
    if ispu <= 199:
        return {"label": "Tidak Sehat", "color": "#eab308", "status": "tidak_sehat"}
    if ispu <= 299:
        return {"label": "Sangat Tidak Sehat", "color": "#ef4444", "status": "sangat_tidak_sehat"}
    return {"label": "Berbahaya", "color": "#1f2937", "status": "berbahaya"}


# ── Gateway & Node Queries ───────────────────────────────────────

def get_gateways(db: Session):
    return db.query(models.Gateway).all()


def get_nodes_by_gateway(db: Session, gateway_id: str):
    return db.query(models.Node).filter(models.Node.gateway_id == gateway_id).all()


def get_node_sensor_trend(db: Session, node_id: str, limit: int = 24):
    return db.query(models.SensorData).filter(
        models.SensorData.node_id == node_id
    ).order_by(models.SensorData.timestamp.desc()).limit(limit).all()

def get_env_config(db: Session, node_id: str):
    return db.query(models.EnvNodeConfig).filter(
        models.EnvNodeConfig.node_id == node_id
    ).first()

def get_vision_config(db: Session, node_id: str):
    return db.query(models.AiVisionConfig).filter(
        models.AiVisionConfig.node_id == node_id
    ).first()


def get_vision_snapshots(db: Session, node_id: str, limit: int = 24):
    return db.query(models.AiVisionSnapshot).filter(
        models.AiVisionSnapshot.node_id == node_id
    ).order_by(models.AiVisionSnapshot.timestamp.desc()).limit(limit).all()


# ── Save Data ────────────────────────────────────────────────────

def save_env_sensor_data(db: Session, gateway_id: str, node_id: str, payload: dict):
    """Save environmental sensor data. Auto-creates gateway/node if new."""
    current_time = datetime.datetime.fromisoformat(payload.get("timestamp")) if "timestamp" in payload else datetime.datetime.utcnow()

    # Ensure gateway exists
    gateway = db.query(models.Gateway).filter(models.Gateway.id == gateway_id).first()
    if not gateway:
        gateway = models.Gateway(
            id=gateway_id,
            name=f"Gateway {gateway_id}",
            company_id="unknown",
            location="Unknown",
            online=True,
            last_update=current_time
        )
        db.add(gateway)
    else:
        gateway.online = True
        gateway.last_update = current_time

    # Ensure node exists
    node = db.query(models.Node).filter(models.Node.id == node_id).first()
    if not node:
        node = models.Node(
            id=node_id,
            gateway_id=gateway_id,
            name=f"Node {node_id}",
            type="environmental",
            zone="Auto-detected",
            online=True
        )
        db.add(node)
    
    current_time = datetime.datetime.fromisoformat(payload.get("timestamp")) if "timestamp" in payload else datetime.datetime.utcnow()
    node.online = True
    node.last_update = current_time

    # Calculate ISPU
    pm25 = payload.get("pm25", 0)
    pm10 = payload.get("pm10", 0)
    co = payload.get("co", 0)
    no2 = payload.get("no2", 0)
    so2 = payload.get("so2", 0)
    o3 = payload.get("o3", 0)
    ispu = calculate_ispu(pm25, pm10, co, no2, so2, o3)

    sensor_data = models.SensorData(
        node_id=node_id,
        gateway_id=gateway_id,
        temperature=payload.get("temperature", 0),
        humidity=payload.get("humidity", 0),
        pm25=pm25,
        pm10=pm10,
        co=co,
        no2=no2,
        so2=so2,
        o3=o3,
        ispu=ispu,
        timestamp=current_time,
    )

    db.add(sensor_data)
    db.commit()
    db.refresh(sensor_data)
    return sensor_data


def save_vision_snapshot(db: Session, gateway_id: str, node_id: str, payload: dict):
    """Save AI Vision detection snapshot. Auto-creates node if new."""
    current_time = datetime.datetime.fromisoformat(payload.get("timestamp")) if "timestamp" in payload else datetime.datetime.utcnow()

    # Ensure gateway exists
    gateway = db.query(models.Gateway).filter(models.Gateway.id == gateway_id).first()
    if not gateway:
        gateway = models.Gateway(
            id=gateway_id,
            name=f"Gateway {gateway_id}",
            company_id="unknown",
            location="Unknown",
            online=True,
            last_update=current_time
        )
        db.add(gateway)
    else:
        gateway.online = True
        gateway.last_update = current_time

    # Ensure node exists
    node = db.query(models.Node).filter(models.Node.id == node_id).first()
    if not node:
        node = models.Node(
            id=node_id,
            gateway_id=gateway_id,
            name=f"Camera {node_id}",
            type="ai_vision",
            zone="Auto-detected",
            online=True
        )
        db.add(node)

        # Create default vision config
        config = models.AiVisionConfig(node_id=node_id)
        db.add(config)
    else:
        node.online = True
        node.last_update = current_time

    # Get room area from config for density calculation
    config = db.query(models.AiVisionConfig).filter(
        models.AiVisionConfig.node_id == node_id
    ).first()
    room_area = config.room_area if config else 100.0

    person_count = payload.get("person_count", 0)
    density = person_count / room_area if room_area > 0 else 0

    # Determine density level
    warning_threshold = config.density_warning if config else 0.1
    alert_threshold = config.density_alert if config else 0.2

    if density >= alert_threshold:
        density_level = "alert"
    elif density >= warning_threshold:
        density_level = "warning"
    else:
        density_level = "normal"

    snapshot = models.AiVisionSnapshot(
        node_id=node_id,
        person_count=person_count,
        density=round(density, 4),
        density_level=density_level,
        timestamp=current_time,
    )

    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def upsert_vision_config(db: Session, node_id: str, config_data: dict):
    """Create or update AI Vision config for a node."""
    config = db.query(models.AiVisionConfig).filter(
        models.AiVisionConfig.node_id == node_id
    ).first()

    if not config:
        config = models.AiVisionConfig(node_id=node_id)
        db.add(config)

    if "stream_url" in config_data:
        config.stream_url = config_data["stream_url"]
    if "room_area" in config_data:
        config.room_area = config_data["room_area"]
    if "confidence_threshold" in config_data:
        config.confidence_threshold = config_data["confidence_threshold"]
    if "density_warning" in config_data:
        config.density_warning = config_data["density_warning"]
    if "density_alert" in config_data:
        config.density_alert = config_data["density_alert"]

    db.commit()
    db.refresh(config)
    return config

def upsert_env_config(db: Session, node_id: str, config_data: dict):
    """Create or update Environmental config for a node."""
    config = db.query(models.EnvNodeConfig).filter(
        models.EnvNodeConfig.node_id == node_id
    ).first()

    if not config:
        config = models.EnvNodeConfig(node_id=node_id)
        db.add(config)

    if "temp_threshold" in config_data:
        config.temp_threshold = config_data["temp_threshold"]
    if "hum_threshold" in config_data:
        config.hum_threshold = config_data["hum_threshold"]
    if "pm25_threshold" in config_data:
        config.pm25_threshold = config_data["pm25_threshold"]
    if "pm10_threshold" in config_data:
        config.pm10_threshold = config_data["pm10_threshold"]
    if "co_threshold" in config_data:
        config.co_threshold = config_data["co_threshold"]
    if "no2_threshold" in config_data:
        config.no2_threshold = config_data["no2_threshold"]
    if "so2_threshold" in config_data:
        config.so2_threshold = config_data["so2_threshold"]
    if "o3_threshold" in config_data:
        config.o3_threshold = config_data["o3_threshold"]

    db.commit()
    db.refresh(config)
    return config


def update_node_info(db: Session, node_id: str, node_data: dict):
    """Update general node information like name and zone."""
    node = db.query(models.Node).filter(models.Node.id == node_id).first()
    if node:
        if "name" in node_data and node_data["name"] is not None:
            node.name = node_data["name"]
        if "zone" in node_data and node_data["zone"] is not None:
            node.zone = node_data["zone"]
        db.commit()
        db.refresh(node)
    return node


def update_gateway_info(db: Session, gateway_id: str, data: dict):
    """Update gateway fields (name, lat, lon)."""
    gw = db.query(models.Gateway).filter(models.Gateway.id == gateway_id).first()
    if gw:
        if "name" in data and data["name"] is not None:
            gw.name = data["name"]
        if "location" in data and data["location"] is not None:
            gw.location = data["location"]
        if "lat" in data and data["lat"] is not None:
            gw.lat = data["lat"]
        if "lon" in data and data["lon"] is not None:
            gw.lon = data["lon"]
        db.commit()
        db.refresh(gw)
    return gw


# ── Seed Data ────────────────────────────────────────────────────

def seed_warehouse_data(db: Session):
    """Seed warehouse gateways and nodes for IKEA Indonesia & Indogrosir."""
    gateways = [
        # IKEA Indonesia
        {
            "id": "GW-IKEA-JKT-01",
            "name": "Gudang IKEA Jakarta Utara",
            "company_id": "comp_ikea_id",
            "location": "Jakarta Utara",
            "lat": -6.1275,
            "lon": 106.8650,
        },
        {
            "id": "GW-IKEA-SBY-01",
            "name": "Gudang IKEA Surabaya",
            "company_id": "comp_ikea_id",
            "location": "Surabaya",
            "lat": -7.2575,
            "lon": 112.7521,
        },
        # Indogrosir
        {
            "id": "GW-INDO-BDG-01",
            "name": "Gudang Indogrosir Bandung",
            "company_id": "comp_indogrosir",
            "location": "Bandung",
            "lat": -6.9271,
            "lon": 107.6411,
        },
        {
            "id": "GW-INDO-MDN-01",
            "name": "Gudang Indogrosir Medan",
            "company_id": "comp_indogrosir",
            "location": "Medan",
            "lat": 3.5952,
            "lon": 98.6722,
        },
    ]

    nodes = [
        # IKEA Jakarta nodes
        {"id": "ENV-IKEA-JKT-001", "gateway_id": "GW-IKEA-JKT-01", "name": "Zone A - Rack Storage", "type": "environmental", "zone": "Zone A"},
        {"id": "ENV-IKEA-JKT-002", "gateway_id": "GW-IKEA-JKT-01", "name": "Zone B - Cold Storage", "type": "environmental", "zone": "Zone B"},
        {"id": "CAM-IKEA-JKT-001", "gateway_id": "GW-IKEA-JKT-01", "name": "Loading Dock Camera", "type": "ai_vision", "zone": "Loading Dock"},
        # IKEA Surabaya nodes
        {"id": "ENV-IKEA-SBY-001", "gateway_id": "GW-IKEA-SBY-01", "name": "Zone A - Main Floor", "type": "environmental", "zone": "Zone A"},
        {"id": "CAM-IKEA-SBY-001", "gateway_id": "GW-IKEA-SBY-01", "name": "Main Entrance Camera", "type": "ai_vision", "zone": "Entrance"},
        # Indogrosir Bandung nodes
        {"id": "ENV-INDO-BDG-001", "gateway_id": "GW-INDO-BDG-01", "name": "Zone A - Dry Goods", "type": "environmental", "zone": "Zone A"},
        {"id": "ENV-INDO-BDG-002", "gateway_id": "GW-INDO-BDG-01", "name": "Zone B - Frozen Section", "type": "environmental", "zone": "Zone B"},
        {"id": "CAM-INDO-BDG-001", "gateway_id": "GW-INDO-BDG-01", "name": "Warehouse Floor Camera", "type": "ai_vision", "zone": "Main Floor"},
        # Indogrosir Medan nodes
        {"id": "ENV-INDO-MDN-001", "gateway_id": "GW-INDO-MDN-01", "name": "Zone A - General Storage", "type": "environmental", "zone": "Zone A"},
        {"id": "CAM-INDO-MDN-001", "gateway_id": "GW-INDO-MDN-01", "name": "Parking Area Camera", "type": "ai_vision", "zone": "Parking"},
    ]

    vision_configs = [
        {"node_id": "CAM-IKEA-JKT-001", "room_area": 500.0, "density_warning": 0.08, "density_alert": 0.15},
        {"node_id": "CAM-IKEA-SBY-001", "room_area": 300.0, "density_warning": 0.1, "density_alert": 0.2},
        {"node_id": "CAM-INDO-BDG-001", "room_area": 400.0, "density_warning": 0.1, "density_alert": 0.2},
        {"node_id": "CAM-INDO-MDN-001", "room_area": 250.0, "density_warning": 0.12, "density_alert": 0.25},
    ]

    for gw in gateways:
        existing = db.query(models.Gateway).filter(models.Gateway.id == gw["id"]).first()
        if not existing:
            db.add(models.Gateway(**gw))

    for nd in nodes:
        existing = db.query(models.Node).filter(models.Node.id == nd["id"]).first()
        if not existing:
            db.add(models.Node(**nd))

    for vc in vision_configs:
        existing = db.query(models.AiVisionConfig).filter(
            models.AiVisionConfig.node_id == vc["node_id"]
        ).first()
        if not existing:
            db.add(models.AiVisionConfig(**vc))

    db.commit()

# ── Historical Analytics ─────────────────────────────────────────
from sqlalchemy import func

import urllib.request
import urllib.parse
import json
import time

def get_historical_telemetry(db: Session, node_ids: list[str], metric: str, time_range: str):
    if not node_ids:
        return {"chartData": [], "kpiData": {}}
        
    now = time.time()
    
    if time_range == '1h':
        start_time = now - 3600
        step = '1m'
    elif time_range == '24h':
        start_time = now - 86400
        step = '1h'
    elif time_range == '7d':
        start_time = now - (7 * 86400)
        step = '1d'
    elif time_range == '30d':
        start_time = now - (30 * 86400)
        step = '1d'
    else:
        start_time = now - 86400
        step = '1h'
        
    # Mapping nama metrik (misal: temperature -> sinergi_temperature)
    prom_metric = f"sinergi_{metric}"
    node_regex = "|".join(node_ids)
    base_query = f'{prom_metric}{{node_id=~"{node_regex}"}}'
    
    import os
    prom_url = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
    
    # 1. Chart Data Query (menggunakan query_range)
    chart_url = f"{prom_url}/api/v1/query_range"
    chart_data_payload = urllib.parse.urlencode({
        'query': base_query,
        'start': start_time,
        'end': now,
        'step': step
    }).encode('utf-8')
    
    kpi_url = f"{prom_url}/api/v1/query"
    
    def fetch_prom(url, payload):
        req = urllib.request.Request(url, data=payload)
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))['data']['result']
            
    try:
        # Menarik data grafik (Time-Series)
        chart_result = fetch_prom(chart_url, chart_data_payload)
        
        time_series_map = {}
        for series in chart_result:
            nid = series['metric'].get('node_id')
            if not nid: continue
            
            for val in series['values']:
                t_sec = val[0]
                v = float(val[1])
                t_iso = datetime.datetime.utcfromtimestamp(t_sec).isoformat()
                
                if t_iso not in time_series_map:
                    time_series_map[t_iso] = {"timestamp": t_iso}
                time_series_map[t_iso][nid] = round(v, 2)
                
        chartData = list(time_series_map.values())
        chartData.sort(key=lambda x: x["timestamp"])
        
        # Menyiapkan KPI Data awal
        kpiData = {nid: {"avg": 0, "min": 0, "max": 0} for nid in node_ids}
        
        # Fungsi pembantu untuk menarik agregasi KPI
        def run_kpi(func_name, key):
            query = f'{func_name}({prom_metric}{{node_id=~"{node_regex}"}}[{time_range}])'
            payload = urllib.parse.urlencode({'query': query}).encode('utf-8')
            res = fetch_prom(kpi_url, payload)
            for r in res:
                nid = r['metric'].get('node_id')
                if nid and nid in kpiData:
                    kpiData[nid][key] = round(float(r['value'][1]), 2)
                    
        # Eksekusi kueri KPI (Avg, Min, Max)
        run_kpi('avg_over_time', 'avg')
        run_kpi('min_over_time', 'min')
        run_kpi('max_over_time', 'max')
        
        return {
            "chartData": chartData,
            "kpiData": kpiData
        }
    except Exception as e:
        print(f"Error querying Prometheus: {e}")
        return {
            "chartData": [],
            "kpiData": {},
            "error": str(e)
        }

def get_prometheus_latest_state(node_ids: list[str]):
    """Query Prometheus for the latest values of all sinergi_* metrics for the given nodes."""
    if not node_ids:
        return {}
        
    import os
    import urllib.request
    import urllib.parse
    import json
    
    prom_url = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
    query_url = f"{prom_url}/api/v1/query"
    
    # Query all metrics starting with sinergi_ for the specific nodes
    node_regex = "|".join(node_ids)
    query = f'{{__name__=~"sinergi_.*", node_id=~"{node_regex}"}}'
    
    payload = urllib.parse.urlencode({'query': query}).encode('utf-8')
    
    latest_state = {nid: {} for nid in node_ids}
    
    try:
        req = urllib.request.Request(query_url, data=payload)
        with urllib.request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode('utf-8'))['data']['result']
            
            for res in result:
                metric_labels = res['metric']
                metric_name = metric_labels.get('__name__', '')
                node_id = metric_labels.get('node_id')
                
                if not node_id or node_id not in latest_state:
                    continue
                    
                # hapus prefix 'sinergi_'
                key = metric_name.replace('sinergi_', '')
                value = float(res['value'][1])
                timestamp = float(res['value'][0])
                
                latest_state[node_id][key] = value
                
                # Update timestamp for node
                if 'timestamp' not in latest_state[node_id] or timestamp > latest_state[node_id]['timestamp']:
                    latest_state[node_id]['timestamp'] = timestamp
                    
        return latest_state
    except Exception as e:
        print(f"Error querying latest state from Prometheus: {e}")
        return {}


# ── Activity Logs ───────────────────────────────────────────────
import uuid

def create_activity_log(db: Session, action: str, detail: str, user_id: str, username: str, company_id: str):
    log_id = "log_" + str(uuid.uuid4()).replace("-", "")[:8]
    log_entry = models.ActivityLog(
        id=log_id,
        user_id=user_id,
        username=username,
        company_id=company_id,
        action=action,
        detail=detail,
        timestamp=datetime.datetime.utcnow()
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)
    return log_entry

def get_activity_logs(db: Session, company_id: str, limit: int = 100):
    query = db.query(models.ActivityLog)
    if company_id:
        query = query.filter(models.ActivityLog.company_id == company_id)
    return query.order_by(models.ActivityLog.timestamp.desc()).limit(limit).all()

def can_view_all_activity_logs(features: list, company_id: str | None) -> bool:
    return (
        company_id == "comp_fmipa_ugm"
        or "view_all_logs" in features
        or "view_all_activity_logs" in features
        or "view_all_nodes" in features
    )

def clear_activity_logs(db: Session, company_id: str):
    query = db.query(models.ActivityLog)
    if company_id:
        query = query.filter(models.ActivityLog.company_id == company_id)
    deleted_count = query.delete()
    db.commit()
    return deleted_count
