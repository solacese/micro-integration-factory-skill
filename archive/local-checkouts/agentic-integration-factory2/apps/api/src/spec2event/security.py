from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from spec2event.config import get_settings


def require_admin(x_demo_admin_password: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if settings.allow_insecure_local_login and settings.app_env == "development":
        if x_demo_admin_password is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-Demo-Admin-Password header",
            )
    if not x_demo_admin_password or not secrets.compare_digest(
        x_demo_admin_password, settings.demo_admin_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin password"
        )
