import json
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
    model_validator,
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
    notification_url: Secret[AnyUrl]
    refresh_interval: Duration = Field("1m", ge=1, le=24 * 60 * 60)
    premieres_only: bool = False
    include_unmonitored: bool = False
    include_downloaded: bool = True
    include_posters: bool = False
    timezone: TimeZoneName = "UTC"
    log_level: t.Literal["debug", "info", "warning", "error", "critical"] = "info"
    log_format: t.Literal["console", "json"] = "console"
    test_notification: bool = False
    redis_url: Secret[RedisDsn] = "redis://localhost"
    sonarr_username: str = ""
    sonarr_password: SecretStr = ""
    sonarr_headers: Secret[Headers] = Field(default_factory=Headers)
    sonarr_api_key_in_url: bool = False

    @field_validator("sonarr_headers", mode="before")
    @classmethod
    def validate_sonarr_headers(cls, v: t.Any):
        if isinstance(v, str):
            return Headers(TypeAdapter(dict).validate_json(v))
        elif isinstance(v, (dict, Headers)):
            return Headers(v)

        return v

    @model_validator(mode="after")
    def setup_logging(self):
        def sink(message):
            if self.log_format == "json":
                record = message.record

                log = json.dumps(
                    {
                        "time": record["time"].timestamp(),
                        "level": record["level"].name,
                        "message": record["message"],
                    }
                )
            else:
                log = message

            print(log, file=sys.stderr, end="")

        logger.remove()

        logger.add(
            sink=sink,
            level=self.log_level.upper(),
            format="[Terebii] {time} | {level} — {message}",
            colorize=True,
            serialize=self.log_format == "json",
        )

        return self

    @field_serializer("sonarr_headers")
    def serialize_sonarr_headers(self, v: Secret[Headers]):
        return TypeAdapter(dict[str, SecretStr]).validate_python(v.get_secret_value())


@cache
def settings() -> TerebiiSettings:
    return TerebiiSettings()


settings()
