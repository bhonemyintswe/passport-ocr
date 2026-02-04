import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the backend directory
backend_dir = Path(__file__).resolve().parent.parent
env_path = backend_dir / ".env"
load_dotenv(env_path)

print(f"Loading .env from: {env_path}")
print(f"GOOGLE_CLOUD_VISION_API_KEY loaded: {'Yes' if os.getenv('GOOGLE_CLOUD_VISION_API_KEY') else 'No'}")

APP_PASSWORD = os.getenv("APP_PASSWORD", "hotel2024")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Google Cloud Vision API
GOOGLE_CLOUD_VISION_API_KEY = os.getenv("GOOGLE_CLOUD_VISION_API_KEY", "")
