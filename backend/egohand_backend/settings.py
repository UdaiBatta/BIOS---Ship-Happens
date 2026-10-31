"""Django settings for the EgoHand Twin backend.

Local, private service: it reads restricted factory footage and derived outputs, so
- it binds to localhost by default (``runserver 127.0.0.1:8000``);
- only files under EGOHAND_MEDIA_ROOTS can be registered or served;
- an optional bearer token (EGOHAND_API_TOKEN) protects every /api/ endpoint;
- the database and run outputs live under data/ and runs/, which git ignores.

Configuration comes from environment variables so nothing secret is committed.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

SECRET_KEY = os.environ.get("EGOHAND_SECRET_KEY") or secrets.token_urlsafe(48)
DEBUG = os.environ.get("EGOHAND_DEBUG", "0") == "1"
ALLOWED_HOSTS = [h for h in os.environ.get("EGOHAND_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "api",
]

MIDDLEWARE = [
    "django.middleware.gzip.GZipMiddleware",
    "api.middleware.CorsMiddleware",
    "api.middleware.TokenAuthMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.http.ConditionalGetMiddleware",
]

ROOT_URLCONF = "egohand_backend.urls"
WSGI_APPLICATION = "egohand_backend.wsgi.application"

DATA_DIR = Path(os.environ.get("EGOHAND_DATA_DIR", REPO_DIR/"data"/"private"/"backend"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
RUNS_DIR = Path(os.environ.get("EGOHAND_RUNS_DIR", REPO_DIR/"runs"/"backend"))
MODEL_PATH = Path(os.environ.get("EGOHAND_MODEL", REPO_DIR/"models"/"hand_landmarker.task"))
MEDIA_ROOTS = [Path(p).resolve() for p in os.environ.get(
    "EGOHAND_MEDIA_ROOTS", str(REPO_DIR/"data"/"private")).split(os.pathsep) if p]
UPLOAD_DIR = Path(os.environ.get("EGOHAND_UPLOAD_DIR", REPO_DIR/"data"/"private"/"uploads"))
API_TOKEN = os.environ.get("EGOHAND_API_TOKEN", "")
CORS_ALLOWED_ORIGINS = [o for o in os.environ.get(
    "EGOHAND_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,"
                            "http://127.0.0.1:5173").split(",") if o]
GOVERNANCE_FILE = os.environ.get("EGOHAND_GOVERNANCE_FILE", "")
MAX_FRAMES_PER_REQUEST = int(os.environ.get("EGOHAND_MAX_FRAMES_PER_REQUEST", "600"))
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("EGOHAND_DB", str(DATA_DIR/"db.sqlite3")),
        "OPTIONS": {"timeout": 20},
    }
}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "egohand",
                      "OPTIONS": {"MAX_ENTRIES": 256}}}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"
LOGGING = {"version": 1, "disable_existing_loggers": False,
           "handlers": {"console": {"class": "logging.StreamHandler"}},
           "root": {"handlers": ["console"], "level": "INFO"}}
APPEND_SLASH = False

# Experimental assumed-lens lift computed for each run so the viewer can show camera-space 3D
# (always labelled "ASSUMED (not calibrated) · depth unvalidated"). Empty string disables it.
_lift = os.environ.get("EGOHAND_LIFT_HFOV", "150")
LIFT_HFOV = float(_lift) if _lift else None
FRONTEND_DIR = Path(os.environ.get("EGOHAND_FRONTEND_DIR", REPO_DIR/"frontend"/"prototype"))
