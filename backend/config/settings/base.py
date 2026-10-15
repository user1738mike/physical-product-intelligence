import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEBUG = False
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "django.contrib.messages",
    "rest_framework",
    "drf_spectacular",
    "operations",
    "accounts",
    "organizations",
    "audit",
    "products",
    "ingestion",
    "compatibility",
]
MIDDLEWARE = [
    "operations.middleware.TrustedProxyMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "operations.middleware.RequestLogMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
DATABASES = {}
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Private ingestion storage has no public media URL or web route.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    "ingestion": {
        "BACKEND": os.environ.get("INGESTION_STORAGE_BACKEND", "ingestion.storage.PrivateStorage"),
        "OPTIONS": {
            "location": os.environ.get(
                "INGESTION_STORAGE_ROOT", str(BASE_DIR / "media" / "ingestion")
            ),
            "file_permissions_mode": 0o600,
            "directory_permissions_mode": 0o700,
        },
    },
}
INGESTION_ALLOW_UNSCANNED = False
AI_EXTRACTION_ENABLED = os.environ.get("AI_EXTRACTION_ENABLED", "false").lower() == "true"
AI_EXTRACTION_PROVIDER = os.environ.get("AI_EXTRACTION_PROVIDER", "openai")
AI_EXTRACTION_MODEL = os.environ.get("AI_EXTRACTION_MODEL", "").strip()
AI_EXTRACTION_MAX_CONCURRENT = max(
    1, min(8, int(os.environ.get("AI_EXTRACTION_MAX_CONCURRENT", "2")))
)
TRUSTED_PROXY_CIDRS = [
    value.strip() for value in os.environ.get("TRUSTED_PROXY_CIDRS", "").split(",") if value.strip()
]
READINESS_PRIVATE_STORAGE = False
READINESS_DATABASE_ROLE = False
INGESTION_SCANNER = os.environ.get("INGESTION_SCANNER", "")
INGESTION_LIMITS = {
    "upload_bytes": int(os.environ.get("INGESTION_MAX_BYTES", 2 * 1024**2)),
    "rows": int(os.environ.get("INGESTION_MAX_ROWS", 200)),
    "columns": 32,
    "sheets": 5,
    "pages": 10,
    "cell_chars": 2000,
    "text_chars": 500000,
    "archive_entries": 128,
    "unpacked_bytes": 8 * 1024**2,
    "compression_ratio": 100,
    "seconds": 20,
    "storage_bytes": 100 * 1024**2,
}
INGESTION_LIMITS = {
    key: int(os.environ.get(f"INGESTION_LIMIT_{key.upper()}", value))
    for key, value in INGESTION_LIMITS.items()
}
DATA_UPLOAD_MAX_MEMORY_SIZE = 3 * 1024**2
FILE_UPLOAD_MAX_MEMORY_SIZE = 3 * 1024**2
DATA_UPLOAD_MAX_NUMBER_FILES = 1
FILE_UPLOAD_HANDLERS = [
    "ingestion.uploads.BoundedUploadHandler",
    "django.core.files.uploadhandler.MemoryFileUploadHandler",
    "django.core.files.uploadhandler.TemporaryFileUploadHandler",
]
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_RATES": {
        "login": "10/min",
        "register": "5/hour",
        "imports": "120/hour",
        "assessments": "60/hour",
        "extractions": "20/hour",
    },
}
SPECTACULAR_SETTINGS = {
    "ENUM_NAME_OVERRIDES": {
        "NumericRuleAttribute": ["length", "width", "height", "mass"],
        "EvidenceAttribute": [
            "length",
            "width",
            "height",
            "mass",
            "name",
            "brand",
            "manufacturer",
            "category",
            "material",
        ],
        "DeclaredHandlingLevel": ["unit", "inner", "case", "pallet"],
        "PackagingLevel": [
            ("unit", "Unit"),
            ("inner", "Inner pack"),
            ("case", "Case"),
            ("pallet", "Pallet"),
        ],
        "MembershipRole": [("owner", "Owner"), ("admin", "Admin"), ("member", "Member")],
        "AssignableRole": ["admin", "member"],
    },
    "TITLE": "Physical Product Intelligence Cloud API",
    "DESCRIPTION": "Tenant-scoped products, packaging, evidence and reviewable ingestion APIs.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "operations.logging.JsonFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.server": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
