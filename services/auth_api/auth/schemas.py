import re
from typing import Any
from pydantic import BaseModel, EmailStr, field_validator, model_validator, ConfigDict

_PASSWORD_RE = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]).{8,128}$"
)


class RegisterRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    email: EmailStr
    password: str
    display_name: str

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        if not _PASSWORD_RE.match(v):
            raise ValueError(
                "Password must be 8-128 chars with uppercase, lowercase, digit, and symbol."
            )
        return v

    @field_validator("display_name")
    @classmethod
    def sane_name(cls, v: str) -> str:
        v = v.strip()
        if not 1 <= len(v) <= 128:
            raise ValueError("display_name must be 1-128 characters.")
        return v


class LoginRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    email: EmailStr
    password: str


class GoogleAuthRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    id_token: str


class PreferencesUpdate(BaseModel):
    model_config = ConfigDict(strict=True)
    theme: str | None = None
    settings_json: dict[str, Any] | None = None

    @field_validator("theme")
    @classmethod
    def valid_theme(cls, v: str | None) -> str | None:
        if v is not None and v not in {"light", "dark", "system"}:
            raise ValueError("theme must be light, dark, or system.")
        return v


class GuestMigrateRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    guest_actions: list[dict[str, Any]]


class HistoryPage(BaseModel):
    limit: int = 20
    before_id: str | None = None

    @field_validator("limit")
    @classmethod
    def cap_limit(cls, v: int) -> int:
        return min(max(v, 1), 100)
