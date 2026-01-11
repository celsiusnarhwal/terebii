import sys
import typing as t
from functools import cache

import durationpy
from httpx import Headers
from loguru import logger
from pydantic import (
    AnyUrl,
    BeforeValidator,
    Field,
    HttpUrl,
    RedisDsn,
    Secret,
    SecretStr,
    TypeAdapter,
    field_serializer,
    field_validator,
)
from pydantic_extra_types.timezone_name import TimeZoneName
from pydantic_settings import BaseSettings, SettingsConfigDict

Duration = t.Annotated[
    int, BeforeValidator(lambda v: durationpy.from_str(v).total_seconds())
]


class TerebiiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TEREBII_", extra="ignore", env_file=".env"
    )

    sonarr_url: HttpUrl
    sonarr_api_key: SecretStr
    notification_url: AnyUrl
    refresh_interval: Duration = Field("1m", ge=1, le=24 * 60 * 60)
    premieres_only: bool = False
    include_unmonitored: bool = False
    include_posters: bool = False
    timezone: TimeZoneName = "UTC"
    test_notification: bool = False
    sonarr_username: str = ""
    sonarr_password: SecretStr = ""
    sonarr_headers: Secret[Headers] = Field(default_factory=Headers)
    redis_url: Secret[RedisDsn] = "redis://localhost"
    log_level: t.Literal["debug", "info", "warning", "error", "critical"] = "info"
    sonarr_api_key_in_url: bool = False

    @field_validator("sonarr_headers", mode="before")
    def validate_sonarr_headers(cls, v: t.Any):
        if isinstance(v, str):
            return Headers(TypeAdapter(dict).validate_json(v))
        elif isinstance(v, (dict, Headers)):
            return Headers(v)

        return v

    @field_validator("log_level")
    @classmethod
    def setup_logging(cls, v: str):
        logger.remove()
        logger.add(
            sink=sys.stderr,
            level=v.upper(),
            format="[Terebii] {time} | {level} — {message}",
        )

        return v

    @field_serializer("sonarr_headers")
    def serialize_sonarr_headers(self, v: Secret[Headers]):
        return TypeAdapter(dict[str, SecretStr]).validate_python(v.get_secret_value())


@cache
def settings() -> TerebiiSettings:
    return TerebiiSettings()


settings()
