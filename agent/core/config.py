from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Conversion Engine"
    environment: str = "development"

    # LLM via OpenRouter
    openrouter_api_key: str = ""
    openrouter_api_keys: str = ""
    open_router_key_1: str = ""
    open_router_key_2: str = ""
    open_router_key_3: str = ""
    open_router_key_4: str = ""
    open_router_key_5: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "qwen/qwen3-235b-a22b"

    # HubSpot
    hubspot_api_key: str = ""
    hubspot_access_token: str = ""
    hubspot_developer_api_key: str = ""
    hubspot_personal_access_key: str = ""
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
    resend_reply_to_email: str = ""
    resend_webhook_signing_secret: str = ""

    # Outbound safety (Tenacious brief): sink routing unless explicitly enabled
    outbound_enabled: bool = False
    outbound_sink_email: str = ""
    outbound_sink_phone: str = ""

    # Africa's Talking
    africastalking_username: str = "sandbox"
    africastalking_api_key: str = ""
    africastalking_short_code: str = ""

    # Local data and state files
    crunchbase_odm_path: str = "./data/crunchbase_odm_sample.json"
    layoffs_fyi_path: str = "./data/layoffs_fyi.csv"
    sms_suppression_path: str = "./data/sms_suppression.json"
    bench_summary_path: str = "./tenacious_sales_data/seed/bench_summary.json"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def model_post_init(self, __context) -> None:  # type: ignore[override]
        # Back-compat with challenge docs / local envs that used different names.
        # HubSpot MCP expects a private app access token; we store whatever the
        # user provided and let the integration surface auth errors clearly.
        if not self.hubspot_api_key:
            # Prefer the explicit private app token env var if present.
            self.hubspot_api_key = (
                self.hubspot_access_token
                or self.hubspot_personal_access_key
                or self.hubspot_developer_api_key
            )

    @property
    def openrouter_key_pool(self) -> list[str]:
        keys: list[str] = []
        for raw in (self.openrouter_api_keys or "").replace("\n", ",").split(","):
            key = raw.strip()
            if key and key not in keys:
                keys.append(key)
        for key in (
            self.openrouter_api_key,
            self.open_router_key_1,
            self.open_router_key_2,
            self.open_router_key_3,
            self.open_router_key_4,
            self.open_router_key_5,
        ):
            if key and key not in keys:
                keys.append(key)
        return keys


settings = Settings()
