from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import database
import models
import crud
from mqtt_client import start_mqtt_client
import hmac
import hashlib
import base64
import json
import asyncio
import datetime
from typing import Optional
from sqlalchemy import text

JWT_SECRET = "liquidglass_secret_token_2026"


# ── JWT Verification ─────────────────────────────────────────────

def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    if pad != 4:
        s += '=' * pad
    return base64.urlsafe_b64decode(s)


def create_jwt(payload: dict) -> str:
    # 24h expiration
    payload_copy = payload.copy()
    payload_copy['exp'] = int(datetime.datetime.utcnow().timestamp()) + (24 * 3600)
    
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode('utf-8')).decode('utf-8').rstrip('=')
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload_copy).encode('utf-8')).decode('utf-8').rstrip('=')
    
    message = f"{header_b64}.{payload_b64}".encode('utf-8')
    sig = hmac.new(JWT_SECRET.encode('utf-8'), message, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode('utf-8').rstrip('=')
    
    return f"{header_b64}.{payload_b64}.{sig_b64}"

def verify_jwt(token: str):
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        message = f"{header_b64}.{payload_b64}".encode('utf-8')
        expected_sig = hmac.new(JWT_SECRET.encode('utf-8'), message, hashlib.sha256).digest()
        actual_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload_json = _b64url_decode(payload_b64).decode('utf-8')
        payload = json.loads(payload_json)
        if 'exp' in payload and payload['exp'] < datetime.datetime.utcnow().timestamp():
            return None
        return payload
    except Exception as e:
        print(f"JWT error: {e}")
        return None


# ── RBAC ─────────────────────────────────────────────────────────

def get_accessible_gateways(company_id: str, features: list):
    if 'view_all_nodes' in features or company_id == 'comp_fmipa_ugm':
        return None  # None = all gateways
        
    db = database.SessionLocal()
    try:
        # We find gateways that belong to this company
        gateways = db.query(models.Gateway).filter(models.Gateway.company_id == company_id).all()
        claimed_devices = [gw.id for gw in gateways]
        
        # Fallback to hardcoded just in case they haven't been provisioned yet
        COMPANY_GATEWAYS = {
            "comp_ikea_id": ["GW-IKEA-JKT-01", "GW-IKEA-SBY-01"],
            "comp_indogrosir": ["GW-INDO-BDG-01", "GW-INDO-MDN-01"],
        }
        legacy_gateways = COMPANY_GATEWAYS.get(company_id, [])
        
        return list(set(claimed_devices + legacy_gateways))
    finally:
        db.close()

# ── Data Formatting ──────────────────────────────────────────────

def format_env_node(node, env_config, latest_data, hourly_data, online_override=None, last_update_override=None):
    """Format an environmental node with its sensor data."""
    hourly_trend = []
    sensors = []
    ispu_info = {"value": 0, "label": "Offline", "color": "#6b7280", "status": "baik"}

    if latest_data:
        # Calculate ISPU if not provided directly by Prometheus
        if not latest_data.ispu:
            latest_data.ispu = crud.calculate_ispu(
                pm10=latest_data.pm10,
                pm25=latest_data.pm25,
                co=latest_data.co,
                no2=latest_data.no2,
                so2=latest_data.so2,
                o3=latest_data.o3
            )
            
        ispu_info = crud.get_ispu_level(latest_data.ispu)
        ispu_info["value"] = latest_data.ispu

        sensors = [
            {"id": "temperature", "label": "Temperature", "value": latest_data.temperature, "unit": "°C", "threshold": env_config.temp_threshold if env_config else 35, "min": 15, "max": 45},
            {"id": "humidity", "label": "Humidity", "value": latest_data.humidity, "unit": "%", "threshold": env_config.hum_threshold if env_config else 80, "min": 0, "max": 100},
            {"id": "pm25", "label": "PM2.5", "value": latest_data.pm25, "unit": "μg/m³", "threshold": env_config.pm25_threshold if env_config else 55.4},
            {"id": "pm10", "label": "PM10", "value": latest_data.pm10, "unit": "μg/m³", "threshold": env_config.pm10_threshold if env_config else 150},
            {"id": "co", "label": "CO", "value": latest_data.co, "unit": "μg/m³", "threshold": env_config.co_threshold if env_config else 8000},
            {"id": "no2", "label": "NO₂", "value": latest_data.no2, "unit": "μg/m³", "threshold": env_config.no2_threshold if env_config else 200},
            {"id": "so2", "label": "SO₂", "value": latest_data.so2, "unit": "μg/m³", "threshold": env_config.so2_threshold if env_config else 180},
            {"id": "o3", "label": "O₃", "value": latest_data.o3, "unit": "μg/m³", "threshold": env_config.o3_threshold if env_config else 235},
        ]

    if hourly_data:
        for h in hourly_data:
            hourly_trend.append({
                "time": h.timestamp.isoformat(),
                "temperature": h.temperature,
                "humidity": h.humidity,
                "pm25": h.pm25,
                "ispu": h.ispu,
            })
        hourly_trend.reverse()

    return {
        "id": node.id,
        "name": node.name,
        "type": node.type,
        "zone": node.zone,
        "online": online_override if online_override is not None else node.online,
        "lastUpdate": last_update_override if last_update_override is not None else (node.last_update.isoformat() if node.last_update else ""),
        "sensors": sensors,
        "ispu": ispu_info,
        "hourlyTrend": hourly_trend,
        "envConfig": {
            "tempThreshold": env_config.temp_threshold if env_config else 35.0,
            "humThreshold": env_config.hum_threshold if env_config else 80.0,
            "pm25Threshold": env_config.pm25_threshold if env_config else 55.4,
            "pm10Threshold": env_config.pm10_threshold if env_config else 150.0,
            "coThreshold": env_config.co_threshold if env_config else 8000.0,
            "no2Threshold": env_config.no2_threshold if env_config else 200.0,
            "so2Threshold": env_config.so2_threshold if env_config else 180.0,
            "o3Threshold": env_config.o3_threshold if env_config else 235.0,
        } if env_config else None,
    }


def format_vision_node(node, config, latest_snapshot, online_override=None, last_update_override=None):
    """Format an AI Vision node with its config and latest detection."""
    vision_config = None
    last_detection = None

    if config:
        vision_config = {
            "streamUrl": config.stream_url or "",
            "roomArea": config.room_area,
            "confidenceThreshold": config.confidence_threshold,
            "densityWarning": config.density_warning,
            "densityAlert": config.density_alert,
        }

    if latest_snapshot:
        last_detection = {
            "personCount": latest_snapshot.person_count,
            "density": latest_snapshot.density,
            "densityLevel": latest_snapshot.density_level,
            "timestamp": latest_snapshot.timestamp.isoformat(),
        }

    return {
        "id": node.id,
        "name": node.name,
        "type": node.type,
        "zone": node.zone,
        "online": online_override if online_override is not None else node.online,
        "lastUpdate": last_update_override if last_update_override is not None else (node.last_update.isoformat() if node.last_update else ""),
        "visionConfig": vision_config,
        "lastDetection": last_detection,
    }


def format_gateway_data(db, gateway, accessible_gateways=None):
    """Format a gateway with all its nodes."""
    if accessible_gateways is not None and gateway.id not in accessible_gateways:
        return None

    nodes = crud.get_nodes_by_gateway(db, gateway.id)
    formatted_nodes = []

    for node in nodes:
        if node.type == "environmental":
            env_config = crud.get_env_config(db, node.id)
            hourly_data = crud.get_node_sensor_trend(db, node.id, limit=24)
            latest = hourly_data[0] if hourly_data else None
            formatted_nodes.append(format_env_node(node, env_config, latest, hourly_data))
        elif node.type == "ai_vision":
            config = crud.get_vision_config(db, node.id)
            snapshots = crud.get_vision_snapshots(db, node.id, limit=1)
            latest_snap = snapshots[0] if snapshots else None
            formatted_nodes.append(format_vision_node(node, config, latest_snap))

    return {
        "id": gateway.id,
        "name": gateway.name,
        "location": gateway.location,
        "lat": gateway.lat,
        "lon": gateway.lon,
        "online": gateway.online,
        "lastUpdate": gateway.last_update.isoformat() if gateway.last_update else "",
        "nodes": formatted_nodes,
    }


def format_gateway_data_prometheus(db, gateway, prom_state, accessible_gateways=None):
    """Format a gateway with all its nodes, using Prometheus data for latest values."""
    if accessible_gateways is not None and gateway.id not in accessible_gateways:
        return None

    nodes = crud.get_nodes_by_gateway(db, gateway.id)
    formatted_nodes = []
    
    any_node_online = False
    latest_gateway_update = gateway.last_update.isoformat() if gateway.last_update else ""

    for node in nodes:
        node_prom_data = prom_state.get(node.id, {})
        
        # Calculate dynamic online status (5 minutes = 300 seconds threshold)
        ts = node_prom_data.get('timestamp', 0)
        is_online = (datetime.datetime.utcnow().timestamp() - ts) <= 300 if ts else False
        last_update_str = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).isoformat() if ts else (node.last_update.isoformat() if node.last_update else "")
        
        if is_online:
            any_node_online = True
            
        if ts and (not latest_gateway_update or last_update_str > latest_gateway_update):
            latest_gateway_update = last_update_str
        
        if node.type == "environmental":
            env_config = crud.get_env_config(db, node.id)
            
            # Reconstruct latest_data object from Prometheus values
            class MockLatestData:
                def __init__(self, data):
                    self.temperature = data.get('temperature', 0)
                    self.humidity = data.get('humidity', 0)
                    self.pm25 = data.get('pm25', 0)
                    self.pm10 = data.get('pm10', 0)
                    self.co = data.get('co', 0)
                    self.no2 = data.get('no2', 0)
                    self.so2 = data.get('so2', 0)
                    self.o3 = data.get('o3', 0)
                    self.ispu = data.get('ispu', 0)
            
            latest = MockLatestData(node_prom_data) if node_prom_data else None
            
            formatted_nodes.append(format_env_node(node, env_config, latest, [], online_override=is_online, last_update_override=last_update_str))
            
        elif node.type == "ai_vision":
            config = crud.get_vision_config(db, node.id)
            
            # Reconstruct latest_snapshot object from Prometheus values
            class MockLatestSnapshot:
                def __init__(self, data):
                    self.person_count = int(data.get('person_count', 0))
                    self.density = data.get('density', 0)
                    # Simple logic to reconstruct density_level
                    warn = config.density_warning if config else 0.1
                    alert = config.density_alert if config else 0.2
                    if self.density >= alert:
                        self.density_level = "alert"
                    elif self.density >= warn:
                        self.density_level = "warning"
                    else:
                        self.density_level = "normal"
                    
                    # Convert timestamp back to datetime if available
                    ts_data = data.get('timestamp')
                    self.timestamp = datetime.datetime.fromtimestamp(ts_data, tz=datetime.timezone.utc) if ts_data else datetime.datetime.utcnow()

            latest_snap = MockLatestSnapshot(node_prom_data) if node_prom_data else None
            formatted_nodes.append(format_vision_node(node, config, latest_snap, online_override=is_online, last_update_override=last_update_str))

    return {
        "id": gateway.id,
        "name": gateway.name,
        "location": gateway.location,
        "lat": gateway.lat,
        "lon": gateway.lon,
        "online": any_node_online if nodes else gateway.online,
        "lastUpdate": latest_gateway_update,
        "nodes": formatted_nodes,
    }


# ── WebSocket Manager ────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[dict] = []

    async def connect(self, websocket: WebSocket, token: str):
        await websocket.accept()
        try:
            payload = verify_jwt(token)
            if not payload:
                raise Exception("Invalid JWT")
            
            features = payload.get("features", [])
            company_id = payload.get("company_id")
            accessible_gateways = get_accessible_gateways(company_id, features)

            # Send initial full state
            db = database.SessionLocal()
            try:
                gateways = crud.get_gateways(db)
                db_gw_ids = set([gw.id for gw in gateways])
                results = []
                
                # Fetch Prometheus state for all nodes in these gateways
                authorized_node_ids = []
                for gw in gateways:
                    if accessible_gateways is None or gw.id in accessible_gateways:
                        nodes = crud.get_nodes_by_gateway(db, gw.id)
                        authorized_node_ids.extend([n.id for n in nodes])
                
                prom_state = crud.get_prometheus_latest_state(authorized_node_ids)
                
                for gw in gateways:
                    formatted = format_gateway_data_prometheus(db, gw, prom_state, accessible_gateways)
                    if formatted:
                        results.append(formatted)

                # Inject claimed but non-existent gateways as offline/empty
                if accessible_gateways is not None:
                    for gw_id in accessible_gateways:
                        if gw_id not in db_gw_ids:
                            results.append({
                                "id": gw_id,
                                "name": f"Gateway {gw_id[-4:]}",
                                "location": "Pending Setup",
                                "lat": -6.200000,
                                "lon": 106.816666,
                                "online": False,
                                "lastUpdate": "",
                                "nodes": []
                            })

                await websocket.send_json({
                    "type": "INITIAL_STATE",
                    "gateways": results,
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
                })
            finally:
                db.close()

            self.active_connections.append({
                "ws": websocket,
                "accessible_gateways": accessible_gateways,
            })
            return True

        except Exception as e:
            import traceback
            traceback.print_exc()
            await websocket.send_json({"error": f"Unauthorized: {str(e)}"})
            await websocket.close(code=1008)
            return False

    def disconnect(self, websocket: WebSocket):
        self.active_connections = [c for c in self.active_connections if c["ws"] != websocket]

    async def broadcast_gateway_update(self, gateway_id: str):
        """Broadcast updated gateway data to all authorized clients."""
        db = database.SessionLocal()
        try:
            gw = db.query(models.Gateway).filter(models.Gateway.id == gateway_id).first()
            if not gw:
                return

            formatted = format_gateway_data(db, gw)
            if not formatted:
                return

            payload = {
                "type": "GATEWAY_UPDATE",
                "gateway": formatted,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }

            for conn in self.active_connections:
                acc = conn["accessible_gateways"]
                if acc is None or gateway_id in acc:
                    try:
                        await conn["ws"].send_json(payload)
                    except Exception:
                        pass
        finally:
            db.close()

    async def broadcast_system_alert(self, alert_payload: dict):
        """Broadcast system alert to all connected clients."""
        payload = {
            "type": "SYSTEM_ALERT",
            "alert": alert_payload,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        for conn in self.active_connections:
            try:
                await conn["ws"].send_json(payload)
            except Exception:
                pass


manager = ConnectionManager()

# Create DB tables
models.Base.metadata.create_all(bind=database.engine)

# Seed database with users and roles if empty
try:
    from migrate_auth import migrate_auth
    migrate_auth()
except Exception as e:
    print(f"Warning: Failed to run migrate_auth: {e}")

# Ensure badge_color column exists (PostgreSQL specific)
try:
    with database.engine.connect() as conn:
        conn.execute(text("ALTER TABLE roles ADD COLUMN IF NOT EXISTS badge_color VARCHAR DEFAULT '#6b7280'"))
        conn.commit()
except Exception as e:
    print(f"Warning: Failed to ensure badge_color column: {e}")

# Seed warehouse data
db = database.SessionLocal()
try:
    crud.seed_warehouse_data(db)
finally:
    db.close()

tags_metadata = [
    {
        "name": "Authentication & Profile",
        "description": "Registrasi akun pengguna, autentikasi login JWT, manajemen profil, dan preferensi dashboard.",
    },
    {
        "name": "Access Control (RBAC)",
        "description": "Manajemen hak akses berbasis peran (Role-Based Access Control). Buat dan kelola peran kustom, tetapkan izin fitur, dan atur hak akses pengguna.",
    },
    {
        "name": "Telemetry & Monitoring",
        "description": "Status telemetri sensor realtime langsung dari database deret waktu Prometheus serta data tren historis.",
    },
    {
        "name": "Devices & Gateways",
        "description": "Manajemen gateway gudang, pembaruan koordinat GPS (Latitude/Longitude), dan pengaturan node IoT.",
    },
    {
        "name": "Node Configuration",
        "description": "Pengaturan batas ambang batas (threshold) sensor lingkungan serta parameter kamera deteksi AI Vision.",
    },
    {
        "name": "Device Provisioning",
        "description": "Manajemen siklus hidup hardware: pembuatan massal Serial Number & PIN serta klaim perangkat oleh perusahaan.",
    },
    {
        "name": "Activity Logs & Alerts",
        "description": "Pencatatan riwayat audit keamanan sistem, log aktivitas pengguna, dan integrasi webhook Prometheus Alertmanager.",
    },
    {
        "name": "Simulator & Ingestion",
        "description": "Endpoint ingesti data telemetri langsung untuk simulator sensor IoT dan pengujian sistem.",
    },
]

app = FastAPI(
    title="API Backend SINERGI Industrial IoT",
    description="Layanan Backend Platform SINERGI Industrial IoT — terintegrasi dengan Prometheus Telemetry, MQTT EMQX, AI Vision Crowding Detection, dan Multi-tenant RBAC.",
    version="1.0.0",
    openapi_tags=tags_metadata
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Start MQTT Client
mqtt_client = None

@app.on_event("startup")
async def startup_event():
    global mqtt_client
    mqtt_client = start_mqtt_client(manager)


# ── WebSocket Endpoint ───────────────────────────────────────────

@app.websocket("/api/v1/ws/stations")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    connected = await manager.connect(websocket, token)
    if not connected:
        return
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ── REST Endpoints ───────────────────────────────────────────────

import uuid

class RegisterRequest(BaseModel):
    username: str
    password: str
    name: str
    company: str

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/v1/auth/register", tags=["Authentication & Profile"], summary="Registrasi akun pengguna baru")
def register(req: RegisterRequest):
    db = database.SessionLocal()
    try:
        existing = db.query(models.User).filter(models.User.username == req.username).first()
        if existing:
            raise HTTPException(status_code=400, detail="Username already exists")
        
        password_hash = hashlib.sha256(req.password.encode()).hexdigest()
        user_id = "user_" + str(uuid.uuid4()).replace("-", "")[:8]
        company_id = "comp_" + req.company.lower().replace(" ", "_")
        
        new_user = models.User(
            user_id=user_id,
            username=req.username,
            password_hash=password_hash,
            role_id="role_guest",
            name=req.name,
            company=req.company,
            company_id=company_id
        )
        db.add(new_user)
        db.commit()
        return {"success": True, "message": "User registered successfully", "user_id": user_id}
    finally:
        db.close()

class UserProfileUpdate(BaseModel):
    name: str
    company: str
    password: Optional[str] = None

@app.put("/api/v1/auth/me", tags=["Authentication & Profile"], summary="Perbarui profil pengguna")
def update_profile(req: UserProfileUpdate, token: str = Query(...)):
    payload = verify_jwt(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
        
    db = database.SessionLocal()
    try:
        user_id = payload.get("sub")
        user = db.query(models.User).filter(models.User.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        user.name = req.name
        user.company = req.company
        
        if req.password:
            user.password_hash = hashlib.sha256(req.password.encode()).hexdigest()
            
        db.commit()
        return {"success": True, "message": "Profile updated successfully"}
    finally:
        db.close()

@app.post("/api/v1/auth/login", tags=["Authentication & Profile"], summary="Login akun dan dapatkan token JWT")
def login(req: LoginRequest):
    db = database.SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.username == req.username).first()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid username or password")
            
        password_hash = hashlib.sha256(req.password.encode()).hexdigest()
        if user.password_hash != password_hash:
            raise HTTPException(status_code=401, detail="Invalid username or password")
            
        role = db.query(models.Role).filter(models.Role.id == user.role_id).first()
        features = json.loads(role.features) if role else []
        custom_features = json.loads(user.custom_features) if user.custom_features else []
        combined_features = list(set(features + custom_features))
        
        is_plus = any(f not in features for f in custom_features)
        roleDisplay = f"{role.name} plus" if (role and is_plus) else (role.name if role else user.role_id)
        badgeColor = role.badge_color if role else "#6b7280"
        
        payload = {
            "sub": user.user_id,
            "username": user.username,
            "role": user.role_id,
            "name": user.name,
            "company": user.company,
            "company_id": user.company_id,
            "features": combined_features,
            "roleDisplay": roleDisplay,
            "badgeColor": badgeColor
        }
        token = create_jwt(payload)
        
        return {
            "token": token,
            "user": {
                "id": user.user_id,
                "username": user.username,
                "name": user.name,
                "role": user.role_id,
                "company": user.company,
                "companyId": user.company_id,
                "features": combined_features,
                "roleDisplay": roleDisplay,
                "badgeColor": badgeColor
            }
        }
    finally:
        db.close()

@app.get("/api/v1/auth/me", tags=["Authentication & Profile"], summary="Ambil data profil & izin hak akses saat ini")
def get_me(token: str):
    payload = verify_jwt(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
        
    db = database.SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.user_id == payload['sub']).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        role = db.query(models.Role).filter(models.Role.id == user.role_id).first()
        features = json.loads(role.features) if role else []
        custom_features = json.loads(user.custom_features) if user.custom_features else []
        combined_features = list(set(features + custom_features))
        
        return {
            "user": {
                "id": user.user_id,
                "username": user.username,
                "name": user.name,
                "role": user.role_id,
                "company": user.company,
                "companyId": user.company_id,
                "features": combined_features,
                "preferences": json.loads(user.preferences) if user.preferences else {}
            }
        }
    finally:
        db.close()


class PreferencesUpdate(BaseModel):
    preferences: dict

@app.put("/api/v1/auth/me/preferences", tags=["Authentication & Profile"], summary="Perbarui preferensi tampilan dashboard pengguna")
def update_preferences(req: PreferencesUpdate, token: str = Query(...)):
    payload = verify_jwt(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
        
    db = database.SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.user_id == payload['sub']).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        user.preferences = json.dumps(req.preferences)
        db.commit()
        return {"success": True, "message": "Preferences updated"}
    finally:
        db.close()


class RoleCreate(BaseModel):
    name: str
    badgeColor: str
    features: list[str]

class RoleUpdate(BaseModel):
    name: Optional[str] = None
    badgeColor: Optional[str] = None
    features: Optional[list[str]] = None

class UserUpdate(BaseModel):
    role_id: Optional[str] = None
    customFeatures: Optional[list[str]] = None

# ── Users RBAC ──
@app.get("/api/v1/auth/users", tags=["Access Control (RBAC)"], summary="Daftar semua pengguna dan peran yang ditetapkan")
def get_all_users(token: str):
    payload = verify_jwt(token)
    if not payload or 'manage_users' not in payload.get('features', []):
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    db = database.SessionLocal()
    try:
        users = db.query(models.User).all()
        roles = db.query(models.Role).all()
        roles_dict = {r.id: r for r in roles}
        
        result = []
        for u in users:
            role = roles_dict.get(u.role_id)
            c_feats = json.loads(u.custom_features) if u.custom_features else []
            r_feats = json.loads(role.features) if role else []
            
            is_plus = any(f not in r_feats for f in c_feats)
            roleDisplay = f"{role.name} plus" if (role and is_plus) else (role.name if role else u.role_id)
            
            result.append({
                "user_id": u.user_id,
                "username": u.username,
                "name": u.name,
                "company": u.company,
                "company_id": u.company_id,
                "role_id": u.role_id,
                "customFeatures": c_feats,
                "roleDisplay": roleDisplay,
                "badgeColor": role.badge_color if role else "#6b7280"
            })
        return {"users": result}
    finally:
        db.close()

@app.put("/api/v1/auth/users/{user_id}", tags=["Access Control (RBAC)"], summary="Perbarui peran dan izin kustom pengguna")
def update_user_rbac(user_id: str, req: UserUpdate, token: str = Query(...)):
    payload = verify_jwt(token)
    if not payload or 'manage_users' not in payload.get('features', []):
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    db = database.SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        if req.role_id is not None:
            user.role_id = req.role_id
        if req.customFeatures is not None:
            user.custom_features = json.dumps(req.customFeatures)
            
        db.commit()
        return {"success": True}
    finally:
        db.close()

@app.delete("/api/v1/auth/users/{user_id}", tags=["Access Control (RBAC)"], summary="Hapus akun pengguna")
def delete_user_rbac(user_id: str, token: str = Query(...)):
    payload = verify_jwt(token)
    if not payload or 'manage_users' not in payload.get('features', []):
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    if user_id == payload['sub']:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
        
    db = database.SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        db.delete(user)
        db.commit()
        return {"success": True}
    finally:
        db.close()

# ── Roles RBAC ──
@app.get("/api/v1/auth/roles", tags=["Access Control (RBAC)"], summary="Daftar semua peran sistem dan hak aksesnya")
def get_all_roles(token: str):
    payload = verify_jwt(token)
    if not payload or 'manage_roles' not in payload.get('features', []):
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    db = database.SessionLocal()
    try:
        roles = db.query(models.Role).all()
        result = []
        for r in roles:
            result.append({
                "id": r.id,
                "name": r.name,
                "badgeColor": r.badge_color,
                "features": json.loads(r.features) if r.features else []
            })
        return {"roles": result}
    finally:
        db.close()

@app.post("/api/v1/auth/roles", tags=["Access Control (RBAC)"], summary="Buat peran (role) kustom baru")
def create_role(req: RoleCreate, token: str = Query(...)):
    payload = verify_jwt(token)
    if not payload or 'manage_roles' not in payload.get('features', []):
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    db = database.SessionLocal()
    try:
        new_role_id = "role_" + str(uuid.uuid4()).replace("-", "")[:8]
        role = models.Role(
            id=new_role_id,
            name=req.name,
            badge_color=req.badgeColor,
            features=json.dumps(req.features)
        )
        db.add(role)
        db.commit()
        return {"success": True, "role": {
            "id": role.id,
            "name": role.name,
            "badgeColor": role.badge_color,
            "features": req.features
        }}
    finally:
        db.close()

@app.put("/api/v1/auth/roles/{role_id}", tags=["Access Control (RBAC)"], summary="Perbarui izin hak akses peran kustom")
def update_role(role_id: str, req: RoleUpdate, token: str = Query(...)):
    payload = verify_jwt(token)
    if not payload or 'manage_roles' not in payload.get('features', []):
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    db = database.SessionLocal()
    try:
        role = db.query(models.Role).filter(models.Role.id == role_id).first()
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
            
        if req.name is not None:
            role.name = req.name
        if req.badgeColor is not None:
            role.badge_color = req.badgeColor
        if req.features is not None:
            role.features = json.dumps(req.features)
            
        db.commit()
        return {"success": True, "role": {
            "id": role.id,
            "name": role.name,
            "badgeColor": role.badge_color,
            "features": json.loads(role.features) if role.features else []
        }}
    finally:
        db.close()

@app.delete("/api/v1/auth/roles/{role_id}", tags=["Access Control (RBAC)"], summary="Hapus peran kustom")
def delete_role(role_id: str, token: str = Query(...)):
    payload = verify_jwt(token)
    if not payload or 'manage_roles' not in payload.get('features', []):
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    db = database.SessionLocal()
    try:
        role = db.query(models.Role).filter(models.Role.id == role_id).first()
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
            
        db.delete(role)
        db.commit()
        return {"success": True}
    finally:
        db.close()


class EnvConfigUpdate(BaseModel):
    temp_threshold: Optional[float] = None
    hum_threshold: Optional[float] = None
    pm25_threshold: Optional[float] = None
    pm10_threshold: Optional[float] = None
    co_threshold: Optional[float] = None
    no2_threshold: Optional[float] = None
    so2_threshold: Optional[float] = None
    o3_threshold: Optional[float] = None

class VisionConfigUpdate(BaseModel):
    stream_url: Optional[str] = None
    room_area: Optional[float] = None
    confidence_threshold: Optional[float] = None
    density_warning: Optional[float] = None
    density_alert: Optional[float] = None


class NodeUpdate(BaseModel):
    name: Optional[str] = None
    zone: Optional[str] = None


class GatewayUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


@app.post("/api/v1/env/config/{node_id}", tags=["Node Configuration"], summary="Perbarui ambang batas (threshold) alarm sensor lingkungan")
def update_env_config(node_id: str, body: EnvConfigUpdate, background_tasks: BackgroundTasks):
    db = database.SessionLocal()
    try:
        config = crud.upsert_env_config(db, node_id, body.model_dump(exclude_none=True))
        
        # Find gateway_id to broadcast the update to all connected WebSocket clients
        node = db.query(models.Node).filter(models.Node.id == node_id).first()
        if node and mqtt_client is not None:
            background_tasks.add_task(manager.broadcast_gateway_update, node.gateway_id)

        return {"status": "success", "node_id": config.node_id}
    finally:
        db.close()


@app.get("/api/v1/telemetry/monitoring/state", tags=["Telemetry & Monitoring"], summary="Ambil state telemetri terkini langsung dari Prometheus")
def get_monitoring_state(token: str):
    """Endpoint for monitoring page to get the latest state directly from Prometheus."""
    payload = verify_jwt(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
        
    features = payload.get("features", [])
    company_id = payload.get("company_id")
    accessible_gateways = get_accessible_gateways(company_id, features)

    db = database.SessionLocal()
    try:
        gateways = crud.get_gateways(db)
        
        # Collect all node IDs that the user has access to
        authorized_node_ids = []
        authorized_gateways = []
        for gw in gateways:
            if accessible_gateways is None or gw.id in accessible_gateways:
                authorized_gateways.append(gw)
                nodes = crud.get_nodes_by_gateway(db, gw.id)
                for n in nodes:
                    authorized_node_ids.append(n.id)
                    
        # Fetch the latest state of all these nodes from Prometheus
        prom_state = crud.get_prometheus_latest_state(authorized_node_ids)
        
        results = []
        db_gw_ids = set([gw.id for gw in gateways])
        
        for gw in authorized_gateways:
            formatted = format_gateway_data_prometheus(db, gw, prom_state, accessible_gateways)
            if formatted:
                results.append(formatted)

        # Inject claimed but non-existent gateways as offline/empty
        if accessible_gateways is not None:
            for gw_id in accessible_gateways:
                if gw_id not in db_gw_ids:
                    results.append({
                        "id": gw_id,
                        "name": f"Gateway {gw_id[-4:]}",
                        "location": "Pending Setup",
                        "lat": -6.200000,
                        "lon": 106.816666,
                        "online": False,
                        "lastUpdate": "",
                        "nodes": []
                    })

        return {
            "type": "PROMETHEUS_STATE",
            "gateways": results,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
    finally:
        db.close()

@app.put("/api/v1/gateways/{gateway_id}", tags=["Devices & Gateways"], summary="Perbarui informasi gateway gudang dan koordinat GPS")
def update_gateway_info(gateway_id: str, body: GatewayUpdate, background_tasks: BackgroundTasks):
    db = database.SessionLocal()
    try:
        gw = crud.update_gateway_info(db, gateway_id, body.model_dump(exclude_none=True))
        if not gw:
            raise HTTPException(status_code=404, detail="Gateway not found")
        
        # Broadcast gateway update to websocket clients
        if mqtt_client is not None:
            background_tasks.add_task(manager.broadcast_gateway_update, gw.id)
            
        return {"status": "success", "gateway_id": gw.id, "name": gw.name, "lat": gw.lat, "lon": gw.lon}
    finally:
        db.close()


@app.post("/api/v1/nodes/{node_id}", tags=["Devices & Gateways"], summary="Perbarui nama node dan penempatan zona")
def update_node_info(node_id: str, body: NodeUpdate, background_tasks: BackgroundTasks):
    db = database.SessionLocal()
    try:
        node = crud.update_node_info(db, node_id, body.model_dump(exclude_none=True))
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")
        
        # Broadcast gateway update
        if mqtt_client is not None:
            background_tasks.add_task(manager.broadcast_gateway_update, node.gateway_id)
            
        return {"status": "success", "node_id": node.id, "name": node.name, "zone": node.zone}
    finally:
        db.close()


from typing import Dict, Any

@app.post("/api/v1/simulator/ingest/{gateway_id}/{node_id}", tags=["Simulator & Ingestion"], summary="Ingesti payload data telemetri simulasi")
def simulator_ingest(gateway_id: str, node_id: str, payload: Dict[str, Any], background_tasks: BackgroundTasks):
    db = database.SessionLocal()
    try:
        data_type = payload.get("type", "environmental")
        if data_type == "environmental":
            crud.save_env_sensor_data(db, gateway_id, node_id, payload)
        elif data_type == "ai_vision":
            crud.save_vision_snapshot(db, gateway_id, node_id, payload)
        
        # Broadcast gateway update
        background_tasks.add_task(manager.broadcast_gateway_update, gateway_id)
            
        return {"status": "success"}
    finally:
        db.close()

@app.get("/api/v1/telemetry/historical", tags=["Telemetry & Monitoring"], summary="Ambil data deret waktu telemetri historis dari Prometheus")
def get_historical_telemetry_endpoint(node_ids: str = Query(...), metric: str = Query("temperature"), time_range: str = Query("24h")):
    db = database.SessionLocal()
    try:
        node_id_list = [n.strip() for n in node_ids.split(",") if n.strip()]
        result = crud.get_historical_telemetry(db, node_id_list, metric, time_range)
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        return result
    finally:
        db.close()

@app.get("/", tags=["Telemetry & Monitoring"], summary="Pemeriksaan status server backend (Health Check)")
def read_root():
    return {"status": "ok", "message": "SINERGI Industrial IoT Backend is running"}


@app.get("/api/v1/vision/config/{node_id}", tags=["Node Configuration"], summary="Ambil konfigurasi kamera deteksi AI Vision")
def get_vision_config(node_id: str):
    db = database.SessionLocal()
    try:
        config = crud.get_vision_config(db, node_id)
        if not config:
            raise HTTPException(status_code=404, detail="Vision config not found")
        return {
            "node_id": config.node_id,
            "stream_url": config.stream_url,
            "room_area": config.room_area,
            "confidence_threshold": config.confidence_threshold,
            "density_warning": config.density_warning,
            "density_alert": config.density_alert,
        }
    finally:
        db.close()


@app.post("/api/v1/vision/config/{node_id}", tags=["Node Configuration"], summary="Perbarui konfigurasi kamera AI Vision")
def update_vision_config(node_id: str, body: VisionConfigUpdate, background_tasks: BackgroundTasks):
    db = database.SessionLocal()
    try:
        config = crud.upsert_vision_config(db, node_id, body.model_dump(exclude_none=True))
        
        # Find gateway_id to broadcast the update to all connected WebSocket clients
        node = db.query(models.Node).filter(models.Node.id == node_id).first()
        if node and mqtt_client is not None:
            background_tasks.add_task(manager.broadcast_gateway_update, node.gateway_id)

        return {
            "node_id": config.node_id,
            "stream_url": config.stream_url,
            "room_area": config.room_area,
            "confidence_threshold": config.confidence_threshold,
            "density_warning": config.density_warning,
            "density_alert": config.density_alert,
        }
    finally:
        db.close()

# ── Provisioning & Device Registry ───────────────────────────────

class DeviceGenerateRequest(BaseModel):
    count: int = 1

class DeviceClaimRequest(BaseModel):
    sn: str
    pin: str

@app.get("/api/v1/provisioning/devices", tags=["Device Provisioning"], summary="Daftar semua perangkat gateway yang terdaftar di sistem")
def get_all_devices():
    db = database.SessionLocal()
    try:
        devices = db.query(models.DeviceRegistry).all()
        return {
            "success": True,
            "devices": [
                {
                    "sn": d.sn,
                    "pin": d.pin,
                    "status": d.status,
                    "company_id": d.company_id,
                    "created_at": d.created_at.isoformat() if d.created_at else None
                } for d in devices
            ]
        }
    finally:
        db.close()

@app.post("/api/v1/provisioning/devices/generate", tags=["Device Provisioning"], summary="Pembuatan massal Serial Number dan PIN perangkat baru")
def generate_devices(req: DeviceGenerateRequest):
    import random
    
    if req.count < 1 or req.count > 100:
        raise HTTPException(status_code=400, detail="Count must be between 1 and 100")
        
    db = database.SessionLocal()
    try:
        new_devices = []
        for _ in range(req.count):
            random_suffix = ''.join(random.choices("0123456789ABCDEF", k=4))
            sn = f"SN-GW-2026-{random_suffix}"
            pin = str(random.randint(10000000, 99999999))
            
            device = models.DeviceRegistry(
                sn=sn,
                pin=pin,
                status="unclaimed",
                company_id=None
            )
            db.add(device)
            new_devices.append({
                "sn": sn,
                "pin": pin,
                "status": "unclaimed",
                "company_id": None,
                "created_at": datetime.datetime.utcnow().isoformat()
            })
            
        db.commit()
        return {"success": True, "generated": new_devices}
    finally:
        db.close()

@app.post("/api/v1/provisioning/devices/claim", tags=["Device Provisioning"], summary="Klaim perangkat gateway oleh perusahaan pengguna")
def claim_device(req: DeviceClaimRequest, token: str = Query(...)):
    payload = verify_jwt(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
        
    db = database.SessionLocal()
    try:
        device = db.query(models.DeviceRegistry).filter(models.DeviceRegistry.sn == req.sn).first()
        if not device:
            raise HTTPException(status_code=404, detail="Serial Number tidak ditemukan dalam sistem.")
            
        if device.pin != req.pin:
            raise HTTPException(status_code=401, detail="PIN Keamanan salah.")
            
        if device.status != "unclaimed":
            raise HTTPException(status_code=400, detail="Perangkat ini sudah diklaim oleh perusahaan lain.")
            
        device.status = "active"
        device.company_id = payload.get("company_id")
        db.commit()
        
        return {
            "success": True,
            "message": "Perangkat berhasil diklaim dan dihubungkan ke dashboard Anda."
        }
    finally:
        db.close()


class LogCreate(BaseModel):
    action: str
    detail: str

@app.get("/api/v1/logs", tags=["Activity Logs & Alerts"], summary="Ambil riwayat log aktivitas dan audit keamanan sistem")
def get_logs(token: str = Query(...)):
    payload = verify_jwt(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
        
    db = database.SessionLocal()
    try:
        features = payload.get("features", [])
        company_id = payload.get("company_id")
        filter_company = None if crud.can_view_all_activity_logs(features, company_id) else company_id

        logs = crud.get_activity_logs(db, company_id=filter_company)
        
        result = []
        for log in logs:
            result.append({
                "id": log.id,
                "timestamp": log.timestamp.isoformat(),
                "action": log.action,
                "detail": log.detail,
                "username": log.username
            })
            
        return {"logs": result}
    finally:
        db.close()

@app.post("/api/v1/logs", tags=["Activity Logs & Alerts"], summary="Buat entri log aktivitas baru")
def create_log(req: LogCreate, token: str = Query(...)):
    payload = verify_jwt(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
        
    db = database.SessionLocal()
    try:
        crud.create_activity_log(
            db=db,
            action=req.action,
            detail=req.detail,
            user_id=payload.get("sub"),
            username=payload.get("username"),
            company_id=payload.get("company_id")
        )
        return {"success": True}
    finally:
        db.close()

@app.delete("/api/v1/logs", tags=["Activity Logs & Alerts"], summary="Hapus riwayat log aktivitas (Khusus Super Admin)")
def clear_logs(token: str = Query(...)):
    payload = verify_jwt(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
        
    features = payload.get("features", [])
    
    # As requested by the user, only the highest role or those with a specific feature
    # like 'manage_roles' or 'manage_users' or 'clear_logs' can delete.
    if 'manage_roles' not in features and 'manage_users' not in features:
        raise HTTPException(status_code=403, detail="Forbidden: You do not have permission to clear logs.")
        
    db = database.SessionLocal()
    try:
        company_id = payload.get("company_id")
        filter_company = None if crud.can_view_all_activity_logs(features, company_id) else company_id

        deleted_count = crud.clear_activity_logs(db, company_id=filter_company)
        return {"success": True, "deleted": deleted_count}
    finally:
        db.close()

@app.post("/api/v1/alerts/webhook", tags=["Activity Logs & Alerts"], summary="Webhook penerima notifikasi alarm dari Prometheus Alertmanager")
async def alertmanager_webhook(request: Request):
    payload = await request.json()
    db = database.SessionLocal()
    try:
        for alert in payload.get('alerts', []):
            if alert.get('status') == 'firing':
                alert_name = alert['labels'].get('alertname', 'Alert')
                gateway_id = alert['labels'].get('gateway_id', 'Unknown')
                node_id = alert['labels'].get('node_id', 'Unknown')
                summary = alert['annotations'].get('summary', 'System Alert')
                description = alert['annotations'].get('description', '')
                
                crud.create_activity_log(
                    db=db,
                    action="alert",
                    detail=f"[{alert_name}] [{gateway_id}/{node_id}] {summary} - {description}",
                    user_id="system",
                    username="Prometheus Alertmanager",
                    company_id="system"
                )
                
                # Broadcast the alert to WebSocket clients
                alert_payload = {
                    "alertname": alert_name,
                    "gateway_id": gateway_id,
                    "node_id": node_id,
                    "summary": summary,
                    "description": description
                }
                import asyncio
                asyncio.create_task(manager.broadcast_system_alert(alert_payload))
        return {"status": "success"}
    except Exception as e:
        print(f"Webhook error: {e}")
        return {"status": "error", "detail": str(e)}
    finally:
        db.close()
