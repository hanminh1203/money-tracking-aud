"""Django settings for the finance-dashboard API."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-dev-only-change-me')
DEBUG = os.environ.get('DJANGO_DEBUG', 'true').lower() in ('1', 'true', 'yes')

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1,.vercel.app').split(',')
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

# Sheets remain the source of truth for reads. Postgres mirrors writes for
# Transactions / Receipt / Receipt_Items (local Docker by default).
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'finance'),
        'USER': os.environ.get('POSTGRES_USER', 'finance'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'finance'),
        'HOST': os.environ.get('POSTGRES_HOST', '127.0.0.1'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
    }
}

SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = False  # SPA must read csrftoken for X-CSRFToken
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = not DEBUG

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
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

# Google Sheets
SHEET_ID = os.environ.get('SHEET_ID', '')
TRANSACTIONS_TABLE = os.environ.get('TRANSACTIONS_TABLE', 'Transactions')
COMPUTED_TRANSACTIONS_TABLE = os.environ.get(
    'COMPUTED_TRANSACTIONS_TABLE', 'Computed_Transactions'
)
INCOME_EXPENSE_TABLE = os.environ.get('INCOME_EXPENSE_TABLE', 'Income vs Expense by Month')
CATEGORY_TABLE = os.environ.get('CATEGORY_TABLE', 'Category')
SOURCES_TABLE = os.environ.get('SOURCES_TABLE', 'Sources')
RECEIPT_TABLE = os.environ.get('RECEIPT_TABLE', 'Receipt')
RECEIPT_ITEMS_TABLE = os.environ.get('RECEIPT_ITEMS_TABLE', 'Receipt_Items')

# Groq
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
GROQ_MODEL = os.environ.get('GROQ_MODEL', 'llama-3.3-70b-versatile')
GROQ_VISION_MODEL = os.environ.get(
    'GROQ_VISION_MODEL',
    'meta-llama/llama-4-scout-17b-16e-instruct',
)
