from pathlib import Path
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def load_workspace_env(path):
    if not path.is_file():
        return

    for line_number, raw_line in enumerate(
        path.read_text(encoding='utf-8-sig').splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].lstrip()

        name, separator, value = line.partition('=')
        name = name.strip()
        if not separator or not name or any(character.isspace() for character in name):
            raise ValueError(f'Entrada .env inválida en {path}, línea {line_number}.')

        value = value.strip()
        if value.startswith(("'", '"')):
            quote = value[0]
            closing_quote = value.find(quote, 1)
            if closing_quote < 0:
                raise ValueError(f'Valor .env sin cerrar en {path}, línea {line_number}.')
            remainder = value[closing_quote + 1:].strip()
            if remainder and not remainder.startswith('#'):
                raise ValueError(f'Contenido inesperado en {path}, línea {line_number}.')
            value = value[1:closing_quote]
        else:
            value = value.split(' #', 1)[0].rstrip()

        os.environ.setdefault(name, value)


load_workspace_env(BASE_DIR.parent / '.env')


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError('Falta la variable de entorno SECRET_KEY')
# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
    if h.strip()
]

# 1. Confiar en el túnel de Cloudflare para peticiones seguras (CSRF)
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get('CORS_ALLOWED_ORIGINS', '').split(',')
    if origin.strip()
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',')
    if origin.strip()
]


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Herramientas de terceros
    'rest_framework',

    # Mis Apps
    'users',
    'fleet',
    'bookings',
    'payments',
    'corsheaders',


    'django_apscheduler',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',

    'corsheaders.middleware.CorsMiddleware',

    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

# Autenticación por token firmado para la API (clientes y trabajadores).
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'core.auth.TokenAutenticacion',
    ],
    # Las vistas públicas (catálogo, disponibilidad) permiten lectura anónima;
    # cada ViewSet restringe por rol con sus propias permission_classes.
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
}

# Correo: en desarrollo se imprime en la consola del servidor (se ve al probar).
# En producción se configura SMTP real por variables de entorno.
SMTP_CONFIGURADO = all(
    os.environ.get(variable)
    for variable in ('EMAIL_HOST', 'EMAIL_HOST_USER', 'EMAIL_HOST_PASSWORD')
)
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND') or (
    'django.core.mail.backends.smtp.EmailBackend'
    if SMTP_CONFIGURADO
    else 'django.core.mail.backends.console.EmailBackend'
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'no-reply@rentcar.cl')

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    }
]

"""
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'rentacarv3'),
        'USER': os.environ.get('DB_USER', 'postgres'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'admin'),
        'HOST': os.environ.get('DB_HOST', '127.0.0.1'),
        'PORT': os.environ.get('DB_PORT', '5433'),
    }
}
"""

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ['DB_NAME'],
        'USER': os.environ['DB_USER'],
        'PASSWORD': os.environ['DB_PASSWORD'],
        'HOST': os.environ['DB_HOST'],
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

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


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'America/Santiago'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'






GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
BANK_DATA_ENCRYPTION_KEY = os.environ.get('BANK_DATA_ENCRYPTION_KEY', '')
WEBPAY_COMMERCE_CODE = os.environ.get('WEBPAY_COMMERCE_CODE', '').strip()
WEBPAY_API_KEY = os.environ.get('WEBPAY_API_KEY', '')
WEBPAY_ENV = os.environ.get('WEBPAY_ENV', 'INTEGRATION').strip().upper()
WEBPAY_RETURN_URL = os.environ.get('WEBPAY_RETURN_URL', '')
WEBPAY_FRONTEND_URL = os.environ.get(
    'WEBPAY_FRONTEND_URL', 'http://127.0.0.1:5173'
).rstrip('/')
CANCELATION_FINANCE_EMAIL = os.environ.get('CANCELATION_FINANCE_EMAIL', '')

