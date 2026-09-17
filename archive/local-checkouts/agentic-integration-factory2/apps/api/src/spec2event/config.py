from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


def _normalized_fernet_key(raw: str) -> str:
    try:
        decoded = base64.urlsafe_b64decode(raw.encode())
        if len(decoded) == 32:
            return raw
    except Exception:
        pass
    digest = hashlib.sha256(raw.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_url: str = "http://localhost:8000"
    next_public_app_url: str = "http://localhost:3000"
    next_public_api_base_url: str = "http://localhost:8000"
    database_url: str = "postgresql+psycopg://spec2event:spec2event@localhost:5432/spec2event"
    redis_url: str = "redis://localhost:6379/0"
    app_encryption_key: str = Field(default="dev-key-change-me")
    demo_admin_password: str = "changeme"
    allow_insecure_local_login: bool = True
    repo_root: Path = REPO_ROOT
    templates_root: Path = REPO_ROOT / "templates"
    runs_root: Path = REPO_ROOT / "generated-runs"
    mdk_sample_root: Path = REPO_ROOT / "mdk-reference" / "micro-integration"
    enable_rq: bool = False
    log_level: str = "INFO"
    local_deploy_port: int = 18080
    public_base_url: str | None = None
    aws_region: str = "ca-central-1"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None
    ecr_repository_name: str = "agentic-integration-factory-generated-integrations"
    control_plane_security_group_id: str | None = None
    control_plane_subnet_id: str | None = None
    control_plane_vpc_id: str | None = None
    ephemeral_ec2_ttl_minutes: int = 60

    solace_broker_url: str | None = None
    solace_vpn: str | None = None
    solace_username: str | None = None
    solace_password: str | None = None
    solace_web_messaging_url: str | None = None

    event_portal_base_url: str | None = None
    event_portal_token: str | None = None

    k8s_api_server: str | None = None
    k8s_token: str | None = None
    k8s_namespace: str = "default"
    k8s_ca_cert: str | None = None
    rancher_url: str | None = None
    rancher_token: str | None = None

    container_registry: str | None = None
    container_registry_username: str | None = None
    container_registry_password: str | None = None
    container_image_prefix: str = "ghcr.io/example/spec2event"

    litellm_base_url: str | None = None
    litellm_api_key: str | None = None
    litellm_model: str = "gpt-4o-mini"

    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None

    deploy_ec2_host: str | None = None
    deploy_ec2_ssh_user: str = "ec2-user"
    deploy_ec2_ssh_private_key: str | None = None
    deploy_ec2_port: int = 22

    @property
    def fernet_key(self) -> str:
        return _normalized_fernet_key(self.app_encryption_key)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.runs_root.mkdir(parents=True, exist_ok=True)
    return settings
