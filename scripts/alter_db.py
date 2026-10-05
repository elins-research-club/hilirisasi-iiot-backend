import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./iiot_data.db")
engine = create_engine(DATABASE_URL)

try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN preferences TEXT DEFAULT '{}';"))
        conn.commit()
    print("Successfully added preferences column to users table.")
except Exception as e:
    print(f"Error altering table (it might already exist): {e}")
