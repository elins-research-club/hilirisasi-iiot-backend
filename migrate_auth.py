import json
from database import SessionLocal, engine
import models

# Ensure tables exist
models.Base.metadata.create_all(bind=engine)

import json
from database import SessionLocal, engine
import models

# Ensure tables exist
models.Base.metadata.create_all(bind=engine)

AUTH_DATA = {
  "roles": [
    {
      "id": "role_admin",
      "name": "Developer",
      "badgeColor": "#22c55e",
      "features": ["view_dashboard", "view_maps", "view_monitoring", "view_analytics", "configure_nodes", "view_logs", "export_analytics", "view_settings", "manage_settings", "manage_users", "manage_roles", "manage_nodes", "manage_inventory"]
    },
    {
      "id": "role_operator",
      "name": "Warehouse Manager",
      "badgeColor": "#3b82f6",
      "features": ["view_dashboard", "view_maps", "view_monitoring", "view_analytics", "configure_nodes", "view_logs", "view_settings", "export_analytics"]
    },
    {
      "id": "role_viewer",
      "name": "Safety Officer",
      "badgeColor": "#64e3d4",
      "features": ["view_dashboard", "view_monitoring", "view_analytics", "view_logs", "export_analytics", "configure_nodes"]
    },
    {
      "id": "role_1780830774927_ynk4",
      "name": "Maintenance Technician",
      "badgeColor": "#8b5cf6",
      "features": ["view_maps", "view_monitoring", "view_analytics", "configure_nodes", "manage_nodes"]
    },
    {
      "id": "role_1780830797120_g24w",
      "name": "Security Supervisor",
      "badgeColor": "#ce2c34",
      "features": ["view_dashboard", "view_monitoring", "view_analytics", "view_maps", "view_logs"]
    },
    {
      "id": "role_1780830835476_a5uh",
      "name": "Executive Data Analyst",
      "badgeColor": "#e59524",
      "features": ["view_dashboard", "view_logs", "export_analytics"]
    },
    {
      "id": "role_guest",
      "name": "Guest",
      "badgeColor": "#94a3b8",
      "features": ["view_dashboard", "view_maps", "view_monitoring", "view_analytics"]
    },
    {
      "id": "role_1780846233134_2v2b",
      "name": "Co-Developer",
      "badgeColor": "#bf4a89",
      "features": ["view_dashboard", "view_maps", "configure_nodes", "view_monitoring", "view_analytics", "view_logs", "manage_nodes", "export_analytics", "manage_settings", "manage_inventory", "view_settings"]
    }
  ],
  "users": [
    {
      "user_id": "usr_admin_001",
      "username": "admin",
      "password_hash": "ccf8c8fcd937cf34a979bbdc1442f766e7aca24a01ed2015b97a874a8b4799ae",
      "role_id": "role_admin",
      "customFeatures": [],
      "name": "Hanif Nugraha",
      "company": "FMIPA UGM",
      "company_id": "comp_fmipa_ugm"
    },
    {
      "user_id": "usr_op_ikea_001",
      "username": "operatorIkea",
      "password_hash": "73d54c895caa4085b4efede42314b9ae0beb2909955e4d10252078a2ecef35e0",
      "role_id": "role_operator",
      "customFeatures": [],
      "name": "Budi Santoso",
      "company": "IKEA Indonesia",
      "company_id": "comp_ikea_id"
    },
    {
      "user_id": "usr_vw_ikea_001",
      "username": "viewIkea",
      "password_hash": "f77dfb984f0fbfec0ce9497ab63b213410c735fd0b7f2975902d42c0515e8cb2",
      "role_id": "role_viewer",
      "customFeatures": [],
      "name": "Andi Pratama",
      "company": "IKEA Indonesia",
      "company_id": "comp_ikea_id"
    },
    {
      "user_id": "usr_1780844124390_9f76",
      "username": "joko",
      "password_hash": "86c2d5963ad19bc5b6d4ae1c98e8de31c68f8108ee1475a9f72b2b219a509587",
      "role_id": "role_guest",
      "customFeatures": [],
      "name": "Joko Widodo",
      "company": "Indomaret Jakarta",
      "company_id": "comp_indomaret_jakarta"
    },
    {
      "user_id": "usr_1780845998047_vkp7",
      "username": "iiot",
      "password_hash": "fa986c6635965293ab6abcd405f6a7db5f333fe8a77551420a1c53bc69d4838d",
      "role_id": "role_1780846233134_2v2b",
      "customFeatures": ["manage_inventory", "manage_settings", "export_analytics", "view_logs", "configure_nodes", "manage_nodes", "view_settings"],
      "name": "Tim IIOT",
      "company": "FMIPA UGM",
      "company_id": "comp_fmipa_ugm"
    },
    {
      "user_id": "usr_magang_001",
      "username": "magang",
      "password_hash": "bb5654a2cbfbbece83d0f94d2915c662beee7f58c51b9d5937dbf51b74a3af5f",
      "role_id": "role_operator",
      "customFeatures": [],
      "name": "Siswa Magang",
      "company": "IKEA Indonesia",
      "company_id": "comp_ikea_id"
    }
  ]
}

def migrate_auth():
    db = SessionLocal()
    try:
        data = AUTH_DATA
        
        # Migrate Roles
        for role_data in data.get('roles', []):
            role = db.query(models.Role).filter(models.Role.id == role_data['id']).first()
            if not role:
                role = models.Role(
                    id=role_data['id'],
                    name=role_data['name'],
                    features=json.dumps(role_data.get('features', []))
                )
                db.add(role)
        
        # Migrate Users
        for user_data in data.get('users', []):
            user = db.query(models.User).filter(models.User.user_id == user_data['user_id']).first()
            if not user:
                user = models.User(
                    user_id=user_data['user_id'],
                    username=user_data['username'],
                    password_hash=user_data['password_hash'],
                    role_id=user_data.get('role_id'),
                    custom_features=json.dumps(user_data.get('customFeatures', [])),
                    name=user_data.get('name', ''),
                    company=user_data.get('company', ''),
                    company_id=user_data.get('company_id', '')
                )
                db.add(user)
                
        db.commit()
        print("Successfully migrated auth to database.")
    except Exception as e:
        print(f"Error migrating data: {e}")
    finally:
        db.close()

if __name__ == '__main__':
    migrate_auth()
