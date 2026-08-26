from .base import *


DEBUG = False

_database_url = os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL_UNPOOLED")
if not _database_url:
    raise RuntimeError(
        "Defina DATABASE_URL ou DATABASE_URL_UNPOOLED para usar config.settings.prod."
    )

DATABASES = {
    "default": postgres_database_from_url(_database_url),
}

_vercel_url = os.getenv("VERCEL_URL", "").strip().removeprefix("https://").removeprefix("http://")
if _vercel_url:
    if _vercel_url not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_vercel_url)
    origem_vercel = f"https://{_vercel_url}"
    if origem_vercel not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(origem_vercel)

SECURE_SSL_REDIRECT = get_bool_env("DJANGO_SECURE_SSL_REDIRECT", True)
SESSION_COOKIE_SECURE = get_bool_env("DJANGO_SESSION_COOKIE_SECURE", True)
CSRF_COOKIE_SECURE = get_bool_env("DJANGO_CSRF_COOKIE_SECURE", True)
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = get_bool_env("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", True)
SECURE_HSTS_PRELOAD = get_bool_env("DJANGO_SECURE_HSTS_PRELOAD", True)
