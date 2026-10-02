from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg://postgres.bwhtisbzobjlphhxtemr:kartIK098%40%23@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres"
    REDIS_URL: str = "redis://default:PipLDPghnhgaN3cxIqxcOjF7c2cbY8Qn@neosnug-appealing-liquid-28403.db.redis.io:13573/0"
    SECRET_KEY: str = "replace-with-a-long-random-secret"
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,https://attendai.kartikmewada168.workers.dev"

    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_STORAGE_ENABLED: bool = False
    SUPABASE_ATTENDANCE_BUCKET: str = "attendance-photos"
    SUPABASE_FACE_BUCKET: str = "face-images"

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = "0808cl241093.ies@ipsacademy.org"
    SMTP_PASSWORD: str = "zolkenmsogomxjst"
    SMTP_FROM_EMAIL: str = "0808cl241093.ies@ipsacademy.org"
    SMTP_FROM_NAME: str = "AttendAI"
    SMTP_USE_TLS: bool = True
    OTP_EXPIRE_MINUTES: int = 10
    OTP_RESEND_SECONDS: int = 60

    # Face recognition
    FACE_MODEL: str = "mediapipe"
    FACE_TOLERANCE: float = 0.45

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
