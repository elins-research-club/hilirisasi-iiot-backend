from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text
from database import Base
import datetime


class Gateway(Base):
    __tablename__ = "gateways"

    id = Column(String, primary_key=True, index=True)
    name = Column(String)
    company_id = Column(String, index=True)
    location = Column(String)
    lat = Column(Float, default=0.0)
    lon = Column(Float, default=0.0)
    online = Column(Boolean, default=True)
    last_update = Column(DateTime, default=datetime.datetime.utcnow)


class Node(Base):
    __tablename__ = "nodes"

    id = Column(String, primary_key=True, index=True)
    gateway_id = Column(String, index=True)
    name = Column(String)
    type = Column(String)  # 'environmental' or 'ai_vision'
    zone = Column(String, default="")
    online = Column(Boolean, default=True)
    last_update = Column(DateTime, default=datetime.datetime.utcnow)


class SensorData(Base):
    __tablename__ = "sensor_data"

    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(String, index=True)
    gateway_id = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    # Environmental sensors
    temperature = Column(Float, default=0)
    humidity = Column(Float, default=0)

    # Air Quality
    pm25 = Column(Float, default=0)
    pm10 = Column(Float, default=0)
    co = Column(Float, default=0)
    no2 = Column(Float, default=0)
    so2 = Column(Float, default=0)
    o3 = Column(Float, default=0)

    # ISPU value calculated
    ispu = Column(Integer, default=0)


class AiVisionConfig(Base):
    __tablename__ = "ai_vision_config"

    node_id = Column(String, primary_key=True, index=True)
    stream_url = Column(String, default="")
    room_area = Column(Float, default=100.0)  # m²
    confidence_threshold = Column(Float, default=0.5)
    density_warning = Column(Float, default=0.1)  # orang/m²
    density_alert = Column(Float, default=0.2)  # orang/m²


class AiVisionSnapshot(Base):
    __tablename__ = "ai_vision_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    person_count = Column(Integer, default=0)
    density = Column(Float, default=0.0)  # orang/m²
    density_level = Column(String, default="normal")  # normal, warning, alert

class EnvNodeConfig(Base):
    __tablename__ = "env_node_config"

    node_id = Column(String, primary_key=True, index=True)
    temp_threshold = Column(Float, default=35.0)
    hum_threshold = Column(Float, default=80.0)
    pm25_threshold = Column(Float, default=55.4)
    pm10_threshold = Column(Float, default=150.0)
    co_threshold = Column(Float, default=8000.0)
    no2_threshold = Column(Float, default=200.0)
    so2_threshold = Column(Float, default=180.0)
    o3_threshold = Column(Float, default=235.0)

class Role(Base):
    __tablename__ = "roles"

    id = Column(String, primary_key=True, index=True)
    name = Column(String)
    badge_color = Column(String, default="#6b7280")
    features = Column(Text, default="[]")  # JSON string of features

class User(Base):
    __tablename__ = "users"

    user_id = Column(String, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role_id = Column(String, index=True)
    custom_features = Column(Text, default="[]")  # JSON string of customFeatures
    name = Column(String)
    company = Column(String)
    company_id = Column(String, index=True)
    preferences = Column(Text, default='{}')

class DeviceRegistry(Base):
    __tablename__ = "device_registry"

    sn = Column(String, primary_key=True, index=True)
    pin = Column(String)
    status = Column(String, default="unclaimed")
    company_id = Column(String, index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=True)
    username = Column(String, nullable=True)
    company_id = Column(String, index=True, nullable=True)
    action = Column(String, index=True)
    detail = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
