from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    sfdc_client_id: str = ""
    sfdc_client_secret: str = ""
    sfdc_redirect_uri: str = ""
    jwt_secret: str
    super_admin_jwt_secret: str = ""
    sfdc_api_version: str = "v60.0"
    nango_secret_key: str = ""
    nango_base_url: str = "https://api.nango.dev"
    nango_provider_config_key: str = "salesforce-revengineer-ecp"
    jwt_expiry_seconds: int = 86400


settings = Settings()
