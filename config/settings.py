from pathlib import Path
import os
import sys

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = [host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",") if host.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.repos",
    "apps.research",
    "apps.api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
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
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

if os.getenv("USE_SQLITE_FOR_TESTS", "").lower() == "true" or "pytest" in sys.modules:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "test.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "codebase_agent"),
            "USER": os.getenv("POSTGRES_USER", "codebase_agent"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", "codebase_agent"),
            "HOST": os.getenv("POSTGRES_HOST", "localhost"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
        }
    }

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
}

CELERY_BROKER_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 1800
CELERY_TASK_SOFT_TIME_LIMIT = 1500
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "false").lower() == "true"
CELERY_TASK_EAGER_PROPAGATES = os.getenv("CELERY_TASK_EAGER_PROPAGATES", "false").lower() == "true"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4")

REPO_CACHE_ROOT = Path(os.getenv("REPO_CACHE_ROOT", str(BASE_DIR / "repos-cache"))).resolve()
SAFE_LOCAL_REPO_ROOTS = [
    Path(path.strip()).resolve()
    for path in os.getenv("SAFE_LOCAL_REPO_ROOTS", str(BASE_DIR)).split(",")
    if path.strip()
]

AGENT_MAX_ITERATIONS = int(os.getenv("AGENT_MAX_ITERATIONS", "8"))
AGENT_MAX_TOOL_CALLS = int(os.getenv("AGENT_MAX_TOOL_CALLS", "24"))
AGENT_TOOL_TIMEOUT_SECONDS = int(os.getenv("AGENT_TOOL_TIMEOUT_SECONDS", "8"))
AGENT_SEARCH_MAX_RESULTS = int(os.getenv("AGENT_SEARCH_MAX_RESULTS", "25"))
AGENT_READ_MAX_LINES = int(os.getenv("AGENT_READ_MAX_LINES", "150"))
AGENT_REPO_LOCK_TIMEOUT_SECONDS = int(os.getenv("AGENT_REPO_LOCK_TIMEOUT_SECONDS", "20"))
AGENT_REPO_STALE_LOCK_SECONDS = int(os.getenv("AGENT_REPO_STALE_LOCK_SECONDS", "60"))
AGENT_GIT_CLONE_TIMEOUT_SECONDS = int(os.getenv("AGENT_GIT_CLONE_TIMEOUT_SECONDS", "300"))
