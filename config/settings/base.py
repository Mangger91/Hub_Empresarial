import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent.parent


def load_env_file(env_path):
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def get_bool_env(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "t", "yes", "on"}


def get_list_env(name, default=""):
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


def unique_items(items):
    return list(dict.fromkeys(item for item in items if item))


load_env_file(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "troque-esta-chave")
DEBUG = get_bool_env("DJANGO_DEBUG", False)

ALLOWED_HOSTS = get_list_env("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")
CSRF_TRUSTED_ORIGINS = get_list_env("DJANGO_CSRF_TRUSTED_ORIGINS", "")

VERCEL_URL = os.getenv("VERCEL_URL", "").strip()
if os.getenv("VERCEL"):
    ALLOWED_HOSTS.extend([".vercel.app"])
    CSRF_TRUSTED_ORIGINS.extend(["https://*.vercel.app"])

if VERCEL_URL:
    ALLOWED_HOSTS.append(VERCEL_URL)
    CSRF_TRUSTED_ORIGINS.append(f"https://{VERCEL_URL}")

ALLOWED_HOSTS = unique_items(ALLOWED_HOSTS)
CSRF_TRUSTED_ORIGINS = unique_items(CSRF_TRUSTED_ORIGINS)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "sistema.apps.SistemaConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "sistema.context_processors.layout_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")

if DATABASE_URL:
    import dj_database_url

    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.getenv("DJANGO_SQLITE_PATH", str(BASE_DIR / "db.sqlite3")),
        }
    }

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

AUTHENTICATION_BACKENDS = [
    "sistema.backends.EmailOrUsernameBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 6},
    },
]

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("DJANGO_EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("DJANGO_EMAIL_PORT", "587"))
EMAIL_USE_TLS = get_bool_env("DJANGO_EMAIL_USE_TLS", True)
EMAIL_USE_SSL = get_bool_env("DJANGO_EMAIL_USE_SSL", False)
EMAIL_HOST_USER = os.getenv("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("DJANGO_EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DJANGO_DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)
SERVER_EMAIL = DEFAULT_FROM_EMAIL
CALENDAR_INVITE_FROM_EMAIL = os.getenv("DJANGO_CALENDAR_INVITE_FROM_EMAIL", DEFAULT_FROM_EMAIL)
CALENDAR_REPLY_TO_EMAIL = os.getenv("DJANGO_CALENDAR_REPLY_TO_EMAIL", DEFAULT_FROM_EMAIL)
CALENDAR_ORGANIZER_EMAIL = os.getenv("DJANGO_CALENDAR_ORGANIZER_EMAIL", CALENDAR_INVITE_FROM_EMAIL)
CALENDAR_ORGANIZER_NAME = os.getenv("DJANGO_CALENDAR_ORGANIZER_NAME", "Agenda de Reuniões")
WHATSAPP_AGENDA_WEBHOOK_URL = os.getenv("DJANGO_WHATSAPP_AGENDA_WEBHOOK_URL", "")
WHATSAPP_AGENDA_TOKEN = os.getenv("DJANGO_WHATSAPP_AGENDA_TOKEN", "")
WHATSAPP_AGENDA_REQUEST_TIMEOUT = float(os.getenv("DJANGO_WHATSAPP_AGENDA_REQUEST_TIMEOUT", "10"))

ROTA_MOTOBOY_GEOCODER_URL = os.getenv(
    "DJANGO_ROTA_MOTOBOY_GEOCODER_URL",
    "https://nominatim.openstreetmap.org/search",
)
ROTA_MOTOBOY_ROUTER_URL = os.getenv(
    "DJANGO_ROTA_MOTOBOY_ROUTER_URL",
    "https://router.project-osrm.org",
)
ROTA_MOTOBOY_USER_AGENT = os.getenv(
    "DJANGO_ROTA_MOTOBOY_USER_AGENT",
    "ControleInternoRotas/1.0",
)
ROTA_MOTOBOY_ENDERECO_ESCRITORIO = os.getenv("DJANGO_ROTA_MOTOBOY_ENDERECO_ESCRITORIO", "")
ROTA_MOTOBOY_COMPLEMENTO_ENDERECO = os.getenv("DJANGO_ROTA_MOTOBOY_COMPLEMENTO_ENDERECO", "")
ROTA_MOTOBOY_REQUEST_TIMEOUT = float(os.getenv("DJANGO_ROTA_MOTOBOY_REQUEST_TIMEOUT", "12"))

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
