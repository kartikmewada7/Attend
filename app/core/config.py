from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/attendance_db"
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str = "replace-with-a-long-random-secret"
    CORS_ORIGINS: str = "https://attendai.kartikmewada168.workers.dev"

    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_STORAGE_ENABLED: bool = False
    SUPABASE_ATTENDANCE_BUCKET: str = "attendance-photos"
    SUPABASE_FACE_BUCKET: str = "face-images"

    # Brevo API (configured via environment variable or .env)
    BREVO_API_KEY: str = ""
    BREVO_FROM_EMAIL: str = "kartikmewada168@gmail.com"
    BREVO_FROM_NAME: str = "AttendAI"

    # Luxand.cloud face recognition / verification API
    LUXAND_API_TOKEN: str = ""
    LUXAND_COLLECTION: str = ""

    # Resend API (configured via environment variable or .env)
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "onboarding@resend.dev"

    # SMTP fallback
    #SMTP_HOST: str = "smtp.gmail.com"
    #SMTP_PORT: int = 587
    #SMTP_USERNAME: str = ""
    #SMTP_PASSWORD: str = ""
    #SMTP_FROM_EMAIL: str = ""
    #SMTP_FROM_NAME: str = "AttendAI"
    #SMTP_USE_TLS: bool = True

    OTP_EXPIRE_MINUTES: int = 10
    OTP_RESEND_SECONDS: int = 60

    # Face recognition
    FACE_MODEL: str = "mediapipe"
    FACE_TOLERANCE: float = 0.45

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
