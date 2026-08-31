"""Typed application settings (12-factor, pydantic-settings)."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # LLM
    agent_api_key: str = ""
    agent_base_url: str = "https://api.openai.com/v1"
    agent_model: str = "gpt-4o-mini"
    agent_temperature: float = 0.4
    agent_max_tool_rounds: int = 6
    # Optional free local LLM: when set (or Ollama reachable at localhost:11434),
    # the real agent uses it even without an API key.
    ollama_base_url: str = ""
    embedding_model: str = "text-embedding-3-small"

    # Database
    database_url: str = ""
    database_pool_size: int = 5
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # Vector store
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = "agent_memory"
    vector_memory_top_k: int = 5

    # Tools
    canvas_default_name: str = "Untitled Canvas"
    http_tool_allowlist: str = "*"
    http_tool_timeout_s: float = 10.0
    http_tool_max_bytes: int = 262_144
    exec_python_enabled: bool = True
    exec_python_timeout_s: float = 8.0

    # SaaS / auth
    saas_data_dir: str = ".data"
    supabase_jwt_secret: str = ""
    demo_email: str = "demo@fk.ai"
    demo_password: str = "demo1234"
    public_base_url: str = "http://localhost:3000"

    # SaaS / billing
    payment_provider: str = "auto"  # auto|sandbox|manual|paddle|jazzcash|stripe
    admin_emails: str = ""  # comma separated; empty => only the demo account is admin

    # Paddle (merchant-of-record, international cards; payouts to PK via Payoneer)
    paddle_api_key: str = ""
    paddle_webhook_secret: str = ""
    paddle_price_starter_monthly: str = ""
    paddle_price_starter_yearly: str = ""
    paddle_price_pro_monthly: str = ""
    paddle_price_pro_yearly: str = ""

    # JazzCash merchant gateway (PKR, wallet + cards) — requires merchant account
    jazzcash_merchant_id: str = ""
    jazzcash_password: str = ""
    jazzcash_integrity_salt: str = ""
    jazzcash_base_url: str = ""  # default https://payments.jazzcash.com.pk

    # Manual payment receiver details (works today, no gateway approval)
    jazzcash_account: str = ""
    easypaisa_account: str = ""
    manual_bank_name: str = ""
    manual_iban: str = ""
    manual_account_title: str = ""

    # Kept for the future (overseas entity) — not usable from a PK business today
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    @property
    def jazzcash_all_configured(self) -> bool:
        return bool(self.jazzcash_merchant_id and self.jazzcash_password and self.jazzcash_integrity_salt)

    @property
    def admin_list(self) -> list[str]:
        return [e.strip().lower() for e in self.admin_emails.split(",") if e.strip()]

    def is_admin(self, email: str | None) -> bool:
        if not email:
            return False
        email = email.lower()
        if email in self.admin_list:
            return True
        # Empty admin list => demo account is the controlling admin (dev/demo).
        return not self.admin_list and email == self.demo_email.lower()

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def http_allowlist(self) -> set[str] | None:
        raw = self.http_tool_allowlist.strip()
        if not raw or raw == "*":
            return None  # allow all hosts
        return {h.strip() for h in raw.split(",") if h.strip()}

    @property
    def llm_configured(self) -> bool:
        return bool(self.agent_api_key.strip())

    @property
    def db_configured(self) -> bool:
        return bool(self.database_url.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
