from .base import *


DEBUG = get_bool_env("DJANGO_DEBUG", True)

ALLOWED_HOSTS = os.getenv(
    "DJANGO_ALLOWED_HOSTS",
    "localhost,127.0.0.1"
).split(",")

CSRF_TRUSTED_ORIGINS = os.getenv(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "http://localhost:1120,http://127.0.0.1:1120"
).split(",")

EMAIL_BACKEND = os.getenv(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
)

LOCAL_DB_NAME = os.getenv("DB_NAME", "controle_interno_teste")
LOCAL_DB_HOST = os.getenv("DB_HOST", "localhost")
LOCAL_DB_PORT = os.getenv("DB_PORT", "5432")

if LOCAL_DB_NAME != "controle_interno_teste":
    raise RuntimeError("Ambiente local deve usar DB_NAME=controle_interno_teste.")

if LOCAL_DB_HOST not in {"localhost", "127.0.0.1", "::1"}:
    raise RuntimeError("Ambiente local deve usar DB_HOST=localhost, 127.0.0.1 ou ::1.")

if LOCAL_DB_PORT != "5432":
    raise RuntimeError("Ambiente local deve usar DB_PORT=5432.")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": LOCAL_DB_NAME,
        "USER": os.getenv("DB_USER", "postgres"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": LOCAL_DB_HOST,
        "PORT": LOCAL_DB_PORT,
    }
}
