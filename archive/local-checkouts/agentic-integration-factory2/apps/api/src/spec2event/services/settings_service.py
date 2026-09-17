from __future__ import annotations

from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from spec2event.config import get_settings
from spec2event.models import SettingSecretMetadata

SECRET_FIELDS = {
    "aws_access_key_id",
    "aws_secret_access_key",
    "aws_session_token",
    "solace_broker_url",
    "solace_vpn",
    "solace_username",
    "solace_password",
    "solace_web_messaging_url",
    "event_portal_base_url",
    "event_portal_token",
    "k8s_api_server",
    "k8s_token",
    "k8s_namespace",
    "k8s_ca_cert",
    "rancher_url",
    "rancher_token",
    "container_registry",
    "container_registry_username",
    "container_registry_password",
    "container_image_prefix",
    "litellm_base_url",
    "litellm_api_key",
    "litellm_model",
    "stripe_secret_key",
    "stripe_webhook_secret",
    "deploy_ec2_host",
    "deploy_ec2_ssh_user",
    "deploy_ec2_ssh_private_key",
    "deploy_ec2_port",
    "public_base_url",
}


def _fernet() -> Fernet:
    settings = get_settings()
    return Fernet(settings.fernet_key.encode())


def set_secret(db: Session, key: str, value: str) -> None:
    record = (
        db.query(SettingSecretMetadata)
        .filter(SettingSecretMetadata.secret_name == key)
        .one_or_none()
    )
    encrypted = _fernet().encrypt(value.encode()).decode()
    if record is None:
        record = SettingSecretMetadata(secret_name=key, encrypted_value=encrypted)
        db.add(record)
    else:
        record.encrypted_value = encrypted
    db.flush()


def get_secret(db: Session, key: str) -> str | None:
    record = (
        db.query(SettingSecretMetadata)
        .filter(SettingSecretMetadata.secret_name == key)
        .one_or_none()
    )
    if record is not None:
        return _fernet().decrypt(record.encrypted_value.encode()).decode()
    settings = get_settings()
    fallback = getattr(settings, key, None)
    if fallback in ("", None):
        return None
    return str(fallback)


def update_settings(db: Session, payload: dict[str, Any]) -> None:
    for key, value in payload.items():
        if key not in SECRET_FIELDS:
            continue
        if value in (None, ""):
            continue
        set_secret(db, key, str(value))


def settings_view(db: Session) -> dict[str, Any]:
    return {
        "has_solace_config": all(
            get_secret(db, field)
            for field in ("solace_broker_url", "solace_vpn", "solace_username", "solace_password")
        ),
        "has_event_portal_config": all(
            get_secret(db, field) for field in ("event_portal_base_url", "event_portal_token")
        ),
        "has_lite_llm_config": all(
            get_secret(db, field)
            for field in ("litellm_base_url", "litellm_api_key", "litellm_model")
        ),
        "has_registry_config": all(
            get_secret(db, field)
            for field in (
                "container_registry",
                "container_registry_username",
                "container_registry_password",
                "container_image_prefix",
            )
        ),
        "has_ec2_config": all(
            get_secret(db, field)
            for field in ("deploy_ec2_host", "deploy_ec2_ssh_user", "deploy_ec2_ssh_private_key")
        ),
        "has_aws_config": all(
            get_secret(db, field)
            for field in ("aws_access_key_id", "aws_secret_access_key", "aws_session_token")
        ),
        "public_base_url": get_secret(db, "public_base_url"),
    }


def resolved_credentials(db: Session) -> dict[str, str]:
    return {key: value for key in SECRET_FIELDS if (value := get_secret(db, key)) is not None}
