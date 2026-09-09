import os
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse


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


def get_int_env(name, default):
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return int(value)


def get_float_env(name, default):
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return float(value)


def get_str_env(name, default=""):
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def postgres_database_from_url(database_url):
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL deve usar postgres:// ou postgresql://.")

    database_name = unquote(parsed.path.lstrip("/"))
    if not database_name:
        raise ValueError("DATABASE_URL precisa informar o nome do banco.")

    config = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": database_name,
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or ""),
    }

    options = {key: value for key, value in parse_qsl(parsed.query, keep_blank_values=True)}
    if options:
        config["OPTIONS"] = options

    return config


load_env_file(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "troque-esta-chave")
DEBUG = get_bool_env("DJANGO_DEBUG", False)
ALLOWED_HOSTS = get_list_env("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")
CSRF_TRUSTED_ORIGINS = get_list_env("DJANGO_CSRF_TRUSTED_ORIGINS", "")

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

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
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
LOGIN_REDIRECT_URL = "inicio"
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
EMAIL_HOST = get_str_env("DJANGO_EMAIL_HOST", "")
EMAIL_PORT = get_int_env("DJANGO_EMAIL_PORT", 587)
EMAIL_USE_TLS = get_bool_env("DJANGO_EMAIL_USE_TLS", True)
EMAIL_USE_SSL = get_bool_env("DJANGO_EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = get_float_env("DJANGO_EMAIL_TIMEOUT", 20)
EMAIL_HOST_USER = get_str_env("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = get_str_env("DJANGO_EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = get_str_env("DJANGO_DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)
SERVER_EMAIL = DEFAULT_FROM_EMAIL
CALENDAR_INVITE_FROM_EMAIL = get_str_env("DJANGO_CALENDAR_INVITE_FROM_EMAIL", DEFAULT_FROM_EMAIL)
CALENDAR_REPLY_TO_EMAIL = get_str_env("DJANGO_CALENDAR_REPLY_TO_EMAIL", DEFAULT_FROM_EMAIL)
CALENDAR_ORGANIZER_EMAIL = get_str_env("DJANGO_CALENDAR_ORGANIZER_EMAIL", CALENDAR_INVITE_FROM_EMAIL)
CALENDAR_ORGANIZER_NAME = get_str_env("DJANGO_CALENDAR_ORGANIZER_NAME", "Agenda de Reuniões")
WHATSAPP_CLOUD_API_ENABLED = get_bool_env("DJANGO_WHATSAPP_CLOUD_API_ENABLED", False)
WHATSAPP_CLOUD_API_BASE_URL = get_str_env(
    "DJANGO_WHATSAPP_CLOUD_API_BASE_URL",
    "https://graph.facebook.com",
)
WHATSAPP_CLOUD_API_VERSION = get_str_env("DJANGO_WHATSAPP_CLOUD_API_VERSION", "")
WHATSAPP_CLOUD_API_ACCESS_TOKEN = get_str_env("DJANGO_WHATSAPP_CLOUD_API_ACCESS_TOKEN", "")
WHATSAPP_CLOUD_API_PHONE_NUMBER_ID = get_str_env(
    "DJANGO_WHATSAPP_CLOUD_API_PHONE_NUMBER_ID",
    "",
)
WHATSAPP_CLOUD_API_BUSINESS_ACCOUNT_ID = get_str_env(
    "DJANGO_WHATSAPP_CLOUD_API_BUSINESS_ACCOUNT_ID",
    "",
)
WHATSAPP_CLOUD_API_TEMPLATE_NAME = get_str_env(
    "DJANGO_WHATSAPP_CLOUD_API_TEMPLATE_NAME",
    "hello_world",
)
WHATSAPP_CLOUD_API_TEMPLATE_LANGUAGE = get_str_env(
    "DJANGO_WHATSAPP_CLOUD_API_TEMPLATE_LANGUAGE",
    "en_US",
)
WHATSAPP_CLOUD_API_TEMPLATE_FIELDS = get_list_env(
    "DJANGO_WHATSAPP_CLOUD_API_TEMPLATE_FIELDS",
    "",
)
WHATSAPP_CLOUD_API_DEFAULT_COUNTRY_CODE = get_str_env(
    "DJANGO_WHATSAPP_CLOUD_API_DEFAULT_COUNTRY_CODE",
    "55",
)
WHATSAPP_CLOUD_API_REQUEST_TIMEOUT = get_float_env(
    "DJANGO_WHATSAPP_CLOUD_API_REQUEST_TIMEOUT",
    10,
)

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
ROTA_MOTOBOY_CIDADE_PADRAO = get_str_env("DJANGO_ROTA_MOTOBOY_CIDADE_PADRAO", "")
ROTA_MOTOBOY_ESTADO_PADRAO = get_str_env("DJANGO_ROTA_MOTOBOY_ESTADO_PADRAO", "")
ROTA_MOTOBOY_PAIS_PADRAO = get_str_env("DJANGO_ROTA_MOTOBOY_PAIS_PADRAO", "Brasil")
ROTA_MOTOBOY_COUNTRYCODES = get_str_env("DJANGO_ROTA_MOTOBOY_COUNTRYCODES", "br")
ROTA_MOTOBOY_REQUEST_TIMEOUT = get_float_env("DJANGO_ROTA_MOTOBOY_REQUEST_TIMEOUT", 12)
ROTA_MOTOBOY_GEOCODER_INTERVALO_SEGUNDOS = get_float_env(
    "DJANGO_ROTA_MOTOBOY_GEOCODER_INTERVALO_SEGUNDOS",
    1,
)

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
