"""
Django settings for technicians project.
"""

from pathlib import Path
import os
import dj_database_url
from celery.schedules import crontab
from dotenv import load_dotenv
load_dotenv()

# ── AI backend selection ───────────────────────────────────────────────────────
# Must be set HERE, at the very top of settings, before any import of
# sentence_transformers / transformers / huggingface_hub can occur.
# Setting them inside text_encoder._ensure_loaded() is too late — the
# huggingface_hub library caches its "check for updates" intent at import time.
#
# AI_BACKEND logic:
#   FastEmbed (ONNX Runtime) is the default in-process engine for both local
#   development and production. It runs offline with CPU-quantized ONNX models,
#   requires zero API tokens, has no external network latency, and avoids PyTorch
#   memory overhead (~120 MB RAM vs PyTorch's ~1.5 GB).
os.environ.setdefault('AI_BACKEND', 'fastembed')
os.environ.setdefault('FASTEMBED_MODEL_NAME', 'BAAI/bge-base-en-v1.5')
# ─────────────────────────────────────────────────────────────────────────────

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent




SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-production-fallback-key-for-collectstatic')
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

if DEBUG:
    ALLOWED_HOSTS = ["127.0.0.1", "localhost", "192.168.43.77"]
else:
    raw_hosts = os.environ.get('ALLOWED_HOSTS', '')
    ALLOWED_HOSTS = [h.strip() for h in raw_hosts.split(',') if h.strip()] if raw_hosts else ["*"]
    render_hostname = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
    if render_hostname and render_hostname not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(render_hostname)
    if '.onrender.com' not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append('.onrender.com')
    # Auto-allow Railway domains
    railway_domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN')
    if railway_domain and railway_domain not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(railway_domain)
    if '.railway.app' not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append('.railway.app')
    if '.up.railway.app' not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append('.up.railway.app')



# Trusted origins for CSRF (required for HTTPS / ngrok / custom domains)
# Set env var as comma-separated list, e.g.:
#   CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://abc123.ngrok-free.app
_extra_origins = [
    o.strip()
    for o in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',')
    if o.strip()
]
CSRF_TRUSTED_ORIGINS = [
    'http://127.0.0.1:8000',
    'http://localhost:8000',
    'https://*.onrender.com',
    'https://*.railway.app',
    'https://*.up.railway.app',
    *_extra_origins,
]
render_hostname = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if render_hostname:
    render_origin = f'https://{render_hostname}'
    if render_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(render_origin)
railway_domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN')
if railway_domain:
    railway_origin = f'https://{railway_domain}'
    if railway_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(railway_origin)


# ==================================
# APPLICATIONS
# ==================================

INSTALLED_APPS = [
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "users.apps.UsersConfig",
    "core.apps.CoreConfig",
    "jobs.apps.JobsConfig",
    'django_celery_results',
    'django_celery_beat',
    'django.contrib.humanize',
    'django.contrib.sites',
    'django.contrib.sitemaps',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'allauth.socialaccount.providers.facebook',
    'allauth.socialaccount.providers.linkedin_oauth2',
    'marketplace.apps.MarketplaceConfig',
    'chats.apps.ChatsConfig',
    'verification.apps.VerificationConfig',
    'bot.apps.BotConfig',
    'hiring.apps.HiringConfig',
    'contacts.apps.ContactsConfig',
]


ASGI_APPLICATION = 'technicians.asgi.application'

if not DEBUG and all([
    os.environ.get('CLOUDINARY_CLOUD_NAME'),
    os.environ.get('CLOUDINARY_API_KEY'),
    os.environ.get('CLOUDINARY_API_SECRET'),
]):
    INSTALLED_APPS.extend([
        'cloudinary_storage',
        'cloudinary',
    ])

SITE_ID = 1


# ==================================
# MIDDLEWARE
# ==================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'core.middleware.TerminalErrorLoggingMiddleware',   # Logs production 500 errors to terminal with full context & traceback
    'core.middleware.GlobalRateLimitMiddleware',       # global 300 req/min per-IP backstop
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    'allauth.account.middleware.AccountMiddleware',
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ==================================
# URLS & WSGI
# ==================================

ROOT_URLCONF = "technicians.urls"

WSGI_APPLICATION = "technicians.wsgi.application"

SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"


# ==================================
# TEMPLATES
# ==================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, 'templates')],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "verification.context_processors.verification_context",
            ],
        },
    },
]

if not DEBUG:
    TEMPLATES[0]['APP_DIRS'] = False
    TEMPLATES[0]['OPTIONS']['loaders'] = [
        ('django.template.loaders.cached.Loader', [
            'django.template.loaders.filesystem.Loader',
            'django.template.loaders.app_directories.Loader',
        ]),
    ]


# ==================================
# DATABASE
# ==================================

if DEBUG:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql_psycopg2',
            'NAME': os.environ.get('DB_NAME'),
            'USER': os.environ.get('DB_USER'),
            'PASSWORD': os.environ.get('DB_PASSWORD'),
            'HOST': os.environ.get('DB_HOST'),
            'PORT': os.environ.get('DB_PORT'),
            'CONN_MAX_AGE': 0,
            'OPTIONS': {
                'connect_timeout': 30,
            },
        }
    }
else:
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if DATABASE_URL:
        DATABASES = {
            'default': dj_database_url.config(
                default=DATABASE_URL,
                conn_max_age=600,
                conn_health_checks=True,
                ssl_require=True,
            )
        }
    else:
        # Build-time or unconfigured fallback (allows collectstatic to succeed without DB connection)
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': BASE_DIR / 'build_dummy.sqlite3',
            }
        }


_redis_url = os.environ.get('REDIS_URL', '')

if _redis_url and _redis_url.startswith('rediss://'):
    # Production — Upstash Redis over TLS (rediss://)
    # Pass ssl=True + ssl_cert_reqs=None so asyncio redis skips cert verification
    # (Upstash uses self-signed certs on the free tier)
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [{
                    'address': _redis_url,
                    'ssl_cert_reqs': None,
                }],
                'capacity': 1500,
                'expiry': 10,
            },
        }
    }
elif _redis_url:
    # Production — plain Redis (redis://)
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [_redis_url],
                'capacity': 1500,
                'expiry': 10,
            },
        }
    }
elif not DEBUG:
    # Production without Redis — fallback to InMemoryChannelLayer so WebSockets don't crash
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        }
    }
else:
    # Development — local Redis
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [('127.0.0.1', 6379)],
            },
        }
    }


AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]


# ==================================
# PASSWORD VALIDATION
# ==================================

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_SIGNUP_FIELDS          = ['email*', 'username*', 'password1*', 'password2*']
ACCOUNT_USERNAME_MIN_LENGTH    = 3
ACCOUNT_EMAIL_VERIFICATION     = 'optional'    # change to 'mandatory' if you send verification emails
 
ACCOUNT_ADAPTER           = 'users.adapters.AccountAdapter'
SOCIALACCOUNT_ADAPTER     = 'users.adapters.SocialAccountAdapter'
 
SOCIALACCOUNT_AUTO_SIGNUP = True     # skip the allauth sign-up form; use your own register page
SOCIALACCOUNT_QUERY_EMAIL = True     # always request the email scope
SOCIALACCOUNT_STORE_TOKENS = True    # persist OAuth tokens in the DB (useful for API calls)
 
LOGIN_URL                  = 'signin'
LOGIN_REDIRECT_URL         = 'marketplace:dashboard'
ACCOUNT_LOGOUT_REDIRECT_URL = 'signin'

# ==================================
# INTERNATIONALISATION
# ==================================

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

PHONENUMBER_DEFAULT_REGION = 'NG'

SOCIALACCOUNT_LOGIN_ON_GET = True

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': os.environ.get('GOOGLE_CLIENT_ID', ''),
            'secret':    os.environ.get('GOOGLE_CLIENT_SECRET', ''),
            'key':       '',
        },
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        },
    },

    'facebook': {
        'APP': {
            'client_id': os.environ.get('FACEBOOK_APP_ID', ''),
            'secret':    os.environ.get('FACEBOOK_APP_SECRET', ''),
            'key':       '',
        },
        'METHOD':         'oauth2',
        'SCOPE':          ['email', 'public_profile'],
        'AUTH_PARAMS':    {'auth_type': 'reauthenticate'},
        'FIELDS':         ['id', 'email', 'name', 'first_name', 'last_name'],
        'EXCHANGE_TOKEN': True,
        'VERIFIED_EMAIL': False,
        'VERSION':        'v19.0',
    },
 
    'linkedin_oauth2': {
        'APP': {
            'client_id': os.environ.get('LINKEDIN_CLIENT_ID', ''),
            'secret':    os.environ.get('LINKEDIN_CLIENT_SECRET', ''),
            'key':       '',
        },
        # LinkedIn's "Sign In with LinkedIn using OpenID Connect" product
        # uses these three scopes.
        'SCOPE': ['openid', 'profile', 'email'],
    },
}
 

# ==================================
# STATIC & MEDIA FILES
# ==================================

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').is_dir() else []
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATIC_ROOT.mkdir(parents=True, exist_ok=True)

STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

if DEBUG:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
        },
    }
else:
    CLOUDINARY_STORAGE = {
        'CLOUD_NAME': os.environ.get('CLOUDINARY_CLOUD_NAME', ''),
        'API_KEY':    os.environ.get('CLOUDINARY_API_KEY', ''),
        'API_SECRET': os.environ.get('CLOUDINARY_API_SECRET', ''),
    }

    if all([
        CLOUDINARY_STORAGE['CLOUD_NAME'],
        CLOUDINARY_STORAGE['API_KEY'],
        CLOUDINARY_STORAGE['API_SECRET'],
    ]):
        STORAGES = {
            "default": {
                "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
            },
            "staticfiles": {
                "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
            },
        }
    else:
        STORAGES = {
            "default": {
                "BACKEND": "django.core.files.storage.FileSystemStorage",
            },
            "staticfiles": {
                "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
            },
        }

# WhiteNoise settings
WHITENOISE_AUTOREFRESH        = DEBUG
WHITENOISE_USE_FINDERS        = DEBUG
WHITENOISE_MAX_AGE            = 0 if DEBUG else 31536000
WHITENOISE_ALLOW_ALL_ORIGINS  = False
WHITENOISE_MANIFEST_STRICT    = False  # Never raise 500 ValueError if a staticfile is not in manifest (e.g. Jazzmin bootswatch)


# ==================================
# CACHING
# ==================================

if DEBUG:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake',
            'TIMEOUT': 300,
            'OPTIONS': {
                'MAX_ENTRIES': 1000,
            },
        }
    }
else:
    REDIS_URL = os.environ.get('REDIS_URL')
    if REDIS_URL:
        CACHES = {
            'default': {
                'BACKEND': 'django_redis.cache.RedisCache',
                'LOCATION': REDIS_URL,
                'OPTIONS': {
                    'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                    'CONNECTION_POOL_KWARGS': {
                        'max_connections': 50,
                        'retry_on_timeout': True,
                        'ssl_cert_reqs': None,
                    },
                    'SOCKET_CONNECT_TIMEOUT': 5,
                    'SOCKET_TIMEOUT': 5,
                },
                'KEY_PREFIX': 'globaledge',
                'TIMEOUT': 300,
            }
        }
    else:
        CACHES = {
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                'LOCATION': 'unique-snowflake',
            }
        }


# ==================================
# SESSIONS
# ==================================

SESSION_ENGINE          = 'django.contrib.sessions.backends.cached_db'
SESSION_CACHE_ALIAS     = 'default'
SESSION_COOKIE_AGE      = 1209600   # 2 weeks
SESSION_COOKIE_SECURE   = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_SAVE_EVERY_REQUEST = False


# ==================================
# AUTH
# ==================================

AUTH_USER_MODEL = "users.User"


# ==================================
# CELERY
# ==================================

if DEBUG:
    CELERY_BROKER_URL     = 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
else:
    REDIS_URL = os.environ.get('REDIS_URL')
    if REDIS_URL:
        CELERY_BROKER_URL     = REDIS_URL
        CELERY_RESULT_BACKEND = REDIS_URL
        # Only apply SSL params in prod where the Redis URL uses rediss://
        CELERY_REDIS_BACKEND_USE_SSL = {
            'ssl_cert_reqs': None,
        }
        CELERY_BROKER_USE_SSL = {
            'ssl_cert_reqs': None,
        }
    else:
        # Build-time or offline fallback so collectstatic does not crash
        CELERY_BROKER_URL     = 'redis://localhost:6379/0'
        CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'

CELERY_ACCEPT_CONTENT     = ['json']
CELERY_TASK_SERIALIZER    = 'json'
CELERY_RESULT_SERIALIZER  = 'json'
CELERY_TIMEZONE           = 'Africa/Lagos'
CELERY_TASK_TRACK_STARTED = True

CELERY_BROKER_TRANSPORT_OPTIONS = {
    'visibility_timeout': 3600,
}

# ── Celery Production Scaling & Memory Management ──────────────────────────────
CELERY_TASK_TIME_LIMIT            = 300   # Hard kill task after 5 min
CELERY_TASK_SOFT_TIME_LIMIT       = 240   # Raise SoftTimeLimitExceeded after 4 min
CELERY_WORKER_MAX_TASKS_PER_CHILD = 50    # Recycle worker process every 50 tasks (prevents memory leaks)
CELERY_WORKER_MAX_MEMORY_PER_CHILD = 350000  # 350 MB max RAM per worker before recycling
CELERY_WORKER_PREFETCH_MULTIPLIER = 1     # Take one task at a time so long AI jobs don't starve other tasks

# ── Production Security Headers ────────────────────────────────────────────────
if not DEBUG:
    SECURE_HSTS_SECONDS            = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD            = True
    SECURE_CONTENT_TYPE_NOSNIFF    = True
    X_FRAME_OPTIONS                = 'DENY'

# ==================================
# PAYSTACK
# ==================================

PAYSTACK_SECRET_KEY     = os.environ.get('PAYSTACK_SECRET_KEY', 'sk_test_166306c4fa6512b95030917dbcfaaa25866d2ff0')
PAYSTACK_PUBLIC_KEY     = os.environ.get('PAYSTACK_PUBLIC_KEY', 'pk_test_d487748abaabb52e28f3c13481053902f78f0e1d')
PAYSTACK_CALLBACK_URL   = os.environ.get('PAYSTACK_CALLBACK_URL', 'http://127.0.0.1:8000/escrow/paystack/callback/')
PAYSTACK_WEBHOOK_SECRET = os.environ.get('PAYSTACK_WEBHOOK_SECRET', PAYSTACK_SECRET_KEY)  # Falls back to secret key if not separately set
# ==================================
# DOJAH (KYC / VERIFICATION)
# ==================================

DOJAH_APP_ID  = os.environ.get('DOJAH_APP_ID')
DOJAH_API_KEY = os.environ.get('DOJAH_API_KEY')
DOJAH_BASE_URL = os.environ.get('DOJAH_BASE_URL', 'https://api.dojah.io')

# ==================================
# MESSAGING PROVIDER
# ==================================
# Switch between 'twilio' and 'meta' with a single env-var change + redeploy.
# No code changes required.
BOT_PROVIDER = os.environ.get('BOT_PROVIDER', 'twilio')  # 'twilio' | 'meta'

# --- Twilio (current default) ---
# Used when BOT_PROVIDER=twilio.
# Sign up at https://twilio.com — use the WhatsApp Sandbox for immediate access.
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN  = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_FROM_NUMBER = os.environ.get('TWILIO_FROM_NUMBER', '')  # E.164, e.g. +14155238886

# --- Meta WhatsApp Business Cloud API (switch back once verified) ---
# Used when BOT_PROVIDER=meta.
WHATSAPP_PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID', '')
WHATSAPP_ACCESS_TOKEN    = os.environ.get('WHATSAPP_ACCESS_TOKEN', '')
WHATSAPP_VERIFY_TOKEN    = os.environ.get('WHATSAPP_VERIFY_TOKEN', 'my_verify_token')
WHATSAPP_API_VERSION     = 'v19.0'

# ==================================
# EMAIL
# ==================================



if DEBUG:
    EMAIL_BACKEND  = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST         = 'smtp.gmail.com'
    EMAIL_PORT        = '465'
    EMAIL_USE_SSL       = os.environ.get('EMAIL_USE_SSL', 'True') == 'True'
    EMAIL_USE_TLS       = os.environ.get('EMAIL_USE_TLS', 'False') == 'True'
    EMAIL_HOST_USER     = os.environ.get('EMAIL_HOST_USER')
    EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
    DEFAULT_FROM_EMAIL  = os.environ.get('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER)



# FastEmbed ONNX model cache
os.environ.setdefault('FASTEMBED_CACHE_PATH', str(BASE_DIR / '.fastembed_cache'))
os.environ.setdefault('ENABLE_CLIP', 'False')  # Keep False on 512MB RAM instances to prevent OOM SIGKILL

# Disable symlinks — use real copies of files instead (required on Windows
# unless Developer Mode / symlink privilege is enabled)
os.environ.setdefault('HUGGINGFACE_HUB_SYMLINKS_MODE', 'copy')
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')

SNAPSHOT_HASH = 'e8c3b32edf5434bc2275fc9bab85f82640a19130'

os.environ.setdefault('HF_TOKEN', '')
os.environ.setdefault('TRANSFORMERS_CACHE', os.path.join(os.path.expanduser('~'), '.hf_cache'))
os.environ.setdefault('HF_HOME',            os.path.join(os.path.expanduser('~'), '.hf_cache'))
os.environ.setdefault('SENTENCE_TRANSFORMERS_HOME', os.path.join(os.path.expanduser('~'), '.hf_cache'))
os.environ.setdefault(
    'TEXT_ENCODER_MODEL_PATH',
    os.path.join(
        os.path.expanduser('~'),
        '.hf_cache', 'hub',
        'models--sentence-transformers--all-mpnet-base-v2',
        'snapshots',
        SNAPSHOT_HASH,
    )
)





CELERY_BEAT_SCHEDULE = {
    # ... existing tasks ...

    # Delete unlinked (orphan) chat image uploads older than 24 h
    'cleanup-orphan-chat-attachments': {
        'task':     'chats.tasks.cleanup_orphan_attachments_task',
        'schedule': crontab(hour=3, minute=30),
    },
    # Fix stuck "online" status for users who disconnected abnormally
    'reset-stale-chat-online-status': {
        'task':     'chats.tasks.reset_stale_online_status_task',
        'schedule': crontab(minute='*/10'),
    },
     'compute-trending-hourly': {
        'task': 'marketplace.tasks.compute_trending_task',
        'schedule': crontab(minute=0),
    },
      'recompute-personalised-feeds-nightly': {
        'task': 'marketplace.tasks.recompute_all_personalised_feeds_task',
        'schedule': crontab(hour=1, minute=30),
    },
    'expire-old-jobs-hourly': {
        'task': 'jobs.tasks.expire_old_jobs_task',
        'schedule': crontab(minute=5),
    },
    'auto-complete-orders': {
        'task': 'marketplace.tasks.auto_complete_orders_task',
        'schedule': crontab(minute='*'),  # Run every minute for testing
    },
    'recompute-all-embeddings-daily': {
        'task': 'jobs.tasks.recompute_all_embeddings_task',
        'schedule': crontab(hour=2, minute=0),
    },
    'recompute-all-product-embeddings-daily': {
        'task': 'marketplace.tasks.recompute_all_product_embeddings_task',
        'schedule': crontab(hour=2, minute=30),
    },
}
RECOVERY_CODE = os.environ.get("RECOVERY_CODE")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ==================================
# LOGGING (TERMINAL & PRODUCTION ERRORS)
# ==================================
from technicians.logging_config import get_logging_config

LOGGING = get_logging_config(BASE_DIR, debug=DEBUG)
