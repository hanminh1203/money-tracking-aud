"""Django settings for the finance-dashboard API."""

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

DEBUG = os.environ.get('DJANGO_DEBUG', 'false').lower() in ('1', 'true', 'yes')

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'django-insecure-dev-only-change-me'
    else:
        raise ImproperlyConfigured('DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is false.')

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
    if h.strip()
]

CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        'CSRF_TRUSTED_ORIGINS',
        'http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000',
    ).split(',')
    if o.strip()
]

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.staticfiles',
    'finance',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'finance.middleware.JsonExceptionMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {'context_processors': []},
    },
]

# Local Docker default; production uses DATABASE_URL (Supabase transaction pooler).
DATABASES = {
    'default': dj_database_url.config(
        default='postgres://finance:finance@127.0.0.1:5432/finance',
        conn_max_age=0,  # serverless: never hold connections between invocations
    )
}
if DATABASES['default']['ENGINE'] == 'django.db.backends.postgresql':
    # Supabase transaction pooler (port 6543): no server-side cursors, no prepared statements.
    DATABASES['default']['DISABLE_SERVER_SIDE_CURSORS'] = True
    DATABASES['default'].setdefault('OPTIONS', {})['prepare_threshold'] = None

SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = False  # SPA must read csrftoken for X-CSRFToken
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = not DEBUG

LANGUAGE_CODE = 'en-us'
# Calendar dates ("today", this month, giftcard use) use this zone.
# Australia/Perth is the default (AUD app, primary user, UTC+8, no DST).
# Australia/Sydney would shift dates during AEDT. Not per-user: one process TZ.
TIME_ZONE = os.environ.get('DJANGO_TIME_ZONE', 'Australia/Perth')
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Google OAuth (authorization code flow)
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
GOOGLE_REDIRECT_URI = os.environ.get(
    'GOOGLE_REDIRECT_URI',
    'http://localhost:5173/api/auth/google/callback',
)
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:5173')
GOOGLE_SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
]

# Google Sheets (per-user sheet_id is stored on finance.User)
TRANSACTIONS_TABLE = os.environ.get('TRANSACTIONS_TABLE', 'Transactions')
CATEGORY_TABLE = os.environ.get('CATEGORY_TABLE', 'Category')
SOURCES_TABLE = os.environ.get('SOURCES_TABLE', 'Sources')
RECEIPT_TABLE = os.environ.get('RECEIPT_TABLE', 'Receipt')
RECEIPT_ITEMS_TABLE = os.environ.get('RECEIPT_ITEMS_TABLE', 'Receipt_Items')
GIFTCARD_TABLE = os.environ.get('GIFTCARD_TABLE', 'Giftcard')
PAYMENT_TABLE = os.environ.get('PAYMENT_TABLE', 'Payment')
GIFTCARD_PAYMENT_TABLE = os.environ.get('GIFTCARD_PAYMENT_TABLE', 'GiftcardPayment')
PRODUCT_TABLE = os.environ.get('PRODUCT_TABLE', 'Product')
PRODUCT_ITEMS_TABLE = os.environ.get('PRODUCT_ITEMS_TABLE', 'Product_Items')

# Groq
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
GROQ_MODEL = os.environ.get('GROQ_MODEL', 'llama-3.3-70b-versatile')
GROQ_VISION_MODEL = os.environ.get(
    'GROQ_VISION_MODEL',
    'qwen/qwen3.6-27b',
)
