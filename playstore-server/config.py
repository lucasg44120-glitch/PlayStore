import os

# ⚠️ CHANGE LE MOT DE PASSE ADMIN avant de mettre le serveur en ligne
ADMIN_USER = os.getenv("STORE_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("STORE_ADMIN_PASSWORD", "admin123")

HOST = os.getenv("STORE_HOST", "0.0.0.0")   # 0.0.0.0 = accessible depuis le réseau
PORT = int(os.getenv("STORE_PORT", "8000"))
MAX_UPLOAD_MB = int(os.getenv("STORE_MAX_UPLOAD_MB", "500"))
