import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = 'django-insecure-l1p&t8n^tn22u)j49v2yppbng=rc*%^+n17)w(p8-7)k#a!)w_'
DEBUG = True
ALLOWED_HOSTS = []

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'reviews',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'slr_engine.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'slr_engine.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
GEMINI_RQ_MODEL = os.getenv('GEMINI_RQ_MODEL', 'gemini-2.5-pro')
GEMINI_SCOPUS_MODEL = os.getenv('GEMINI_SCOPUS_MODEL', 'gemini-2.5-pro')
GEMINI_SCREENING_MODEL = os.getenv('GEMINI_SCREENING_MODEL', 'gemini-2.5-flash')
FULLTEXT_SCREENING_CHUNK_SIZE = int(os.getenv('FULLTEXT_SCREENING_CHUNK_SIZE', '5'))
SCREENING_CONFLICT_THRESHOLD = float(os.getenv('SCREENING_CONFLICT_THRESHOLD', '0.72'))
SCREENING_POLL_CHUNK_SIZE = int(os.getenv('SCREENING_POLL_CHUNK_SIZE', '25'))
ELSEVIER_API_KEY = os.getenv('ELSEVIER_API_KEY', '')
ELSEVIER_INSTTOKEN = os.getenv('ELSEVIER_INSTTOKEN', '')
UNPAYWALL_EMAIL = os.getenv('UNPAYWALL_EMAIL', '')
PDF_RETRIEVAL_DELAY_SECONDS = float(os.getenv('PDF_RETRIEVAL_DELAY_SECONDS', '1.0'))
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', '')
DEEPSEEK_BASE_URL = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
DEEPSEEK_SUMMERY_MODEL = os.getenv('DEEPSEEK_SUMMERY_MODEL', 'deepseek-reasoner')
DEEPSEEK_FULLTEXT_MODEL = os.getenv('DEEPSEEK_FULLTEXT_MODEL', 'deepseek-reasoner')
DEEPSEEK_TIMEOUT_SECONDS = float(os.getenv('DEEPSEEK_TIMEOUT_SECONDS', '90'))
DEEPSEEK_REQUEST_DELAY_SECONDS = float(os.getenv('DEEPSEEK_REQUEST_DELAY_SECONDS', '1.0'))


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'






ELSEVIER_DEBUG_TIMEOUT_SECONDS = float(os.getenv('ELSEVIER_DEBUG_TIMEOUT_SECONDS', '30'))
ELSEVIER_DEBUG_DELAY_SECONDS = float(os.getenv('ELSEVIER_DEBUG_DELAY_SECONDS', '1.5'))

MINERU_API_TOKEN = os.getenv('MINERU_API_TOKEN', '')
MINERU_BASE_URL = os.getenv('MINERU_BASE_URL', 'https://mineru.net/api/v4')
MINERU_MODEL_VERSION = os.getenv('MINERU_MODEL_VERSION', 'vlm')
MINERU_TIMEOUT_SECONDS = float(os.getenv('MINERU_TIMEOUT_SECONDS', '30'))
MINERU_POLL_INTERVAL_SECONDS = float(os.getenv('MINERU_POLL_INTERVAL_SECONDS', '5'))
MINERU_MAX_POLLS = int(os.getenv('MINERU_MAX_POLLS', '60'))
MINERU_REQUEST_DELAY_SECONDS = float(os.getenv('MINERU_REQUEST_DELAY_SECONDS', '1.0'))

CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')








