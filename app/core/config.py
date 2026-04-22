from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Conversion Engine"
    environment: str = "development"

    # LLM via OpenRouter
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "qwen/qwen3-235b-a22b"

    # HubSpot
    hubspot_api_key: str = ""
    hubspot_base_url: str = "https://api.hubapi.com"

    # Cal.com self-hosted. If you expose it through ngrok or Cloudflare Tunnel,
    # use the same public URL here and in calcom/.env for NEXT_PUBLIC_WEBAPP_URL.
    calcom_api_key: str = ""
    calcom_base_url: str = "http://localhost:3000"
    calcom_event_type_id: int = 1

    # Langfuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # Resend
    resend_api_key: str = ""
    resend_from_email: str = ""

    # Africa's Talking
    africastalking_username: str = "sandbox"
    africastalking_api_key: str = ""
    africastalking_short_code: str = ""

    # Local data and state files
    crunchbase_odm_path: str = "./data/crunchbase_odm_sample.json"
    layoffs_fyi_path: str = "./data/layoffs_fyi.csv"
    sms_suppression_path: str = "./data/sms_suppression.json"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
