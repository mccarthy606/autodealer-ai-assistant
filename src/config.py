"""Application configuration via Pydantic Settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://postgres:postgres@localhost:5432/autodealer"
    redis_url: str = "redis://localhost:6379/0"

    # OpenAI (optional - system works without it)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    llm_enabled: bool = False

    # WhatsApp Business Cloud API
    whatsapp_cloud_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_webhook_secret: str = ""

    # MercadoLibre
    ml_access_token: str = ""
    ml_refresh_token: str = ""
    ml_user_id: str = ""
    ml_nickname: str = "GRUPOAUTODEAL"
    ml_app_id: str = ""
    ml_client_secret: str = ""

    # Notifications
    manager_webhook_url: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_to: str = ""

    # Security
    allowed_origins: str = ""                    # comma-separated CORS origins
    admin_password_hash: str = ""                # bcrypt hash for admin auth
    lemon_squeezy_webhook_secret: str = ""       # HMAC secret for webhook verification
    ml_webhook_secret: str = ""                  # MercadoLibre notification secret (optional)
    session_cookie_secure: bool = True           # set False only for local HTTP dev

    # App
    default_dealership_id: int = 1
    admin_password: str = ""
    followups_enabled: bool = False
    default_language: str = "es-AR"
    fallback_language: str = "en"

    # Credential encryption (Fernet key for encrypting DB credential columns)
    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    credential_encryption_key: str = ""          # leave empty to store credentials unencrypted (dev only)

    # Monitoring
    sentry_dsn: str = ""                         # Sentry DSN — leave empty to disable
    sentry_environment: str = "production"       # Sentry environment tag
    sentry_release: str = ""                     # Sentry release tag — defaults to app version


settings = Settings()
