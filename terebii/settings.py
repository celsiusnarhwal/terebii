import typing as t
from functools import cache

import durationpy
from pydantic import AnyUrl, BeforeValidator, HttpUrl, RedisDsn, SecretStr, Field
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
    refresh_interval: Duration = Field("1m", ge=1)
    include_posters: bool = False
    redis_url: RedisDsn = "redis://localhost"


@cache
def settings() -> TerebiiSettings:
    return TerebiiSettings()


settings()
