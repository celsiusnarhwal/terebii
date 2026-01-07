import sys
import typing as t
from datetime import datetime
from functools import cache

import durationpy
from loguru import logger
from pydantic import (
    AnyUrl,
    BeforeValidator,
    Field,
    HttpUrl,
    RedisDsn,
    Secret,
    SecretStr,
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
    timezone: TimeZoneName = Field(None, alias="TZ")
    refresh_interval: Duration = Field("1m", ge=1)
    include_unmonitored: bool = False
    include_posters: bool = False
    redis_url: Secret[RedisDsn] = "redis://localhost"
    log_level: t.Literal["debug", "info", "warning", "error"] = "info"

    @field_validator("timezone", mode="before")
    def validate_timezone(cls, v):
        return v or datetime.now().astimezone().tzname()

    @field_validator("log_level")
    @classmethod
    def setup_logging(cls, v):
        logger.remove()
        logger.add(
            sink=sys.stderr,
            level=v.upper(),
            format="[Terebii] {time} | {level} — {message}",
        )

        return v


@cache
def settings() -> TerebiiSettings:
    return TerebiiSettings()


settings()
