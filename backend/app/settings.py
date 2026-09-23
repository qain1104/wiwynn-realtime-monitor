from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = 'mysql+asyncmy://monitor:localpassword@localhost:3306/monitor'
    jwt_secret: str = 'local-development-only-secret-change-me'
    admin_email: str = 'admin@example.com'
    admin_password: str = 'change-this-admin-password'
    alert_threshold: float = 80
    batch_size: int = 10
    realtime_enabled: bool = True
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

settings = Settings()
