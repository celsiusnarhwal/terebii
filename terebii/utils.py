from pathlib import Path

import httpx
import jinja2
from jinja2 import ChoiceLoader, Environment, FileSystemLoader
from loguru import logger

from terebii.settings import settings

fs_loaders = [
    FileSystemLoader(Path(__file__).parent / "templates"),
    FileSystemLoader(Path(__file__).parent / "default_templates"),
]

templates = Environment(
    loader=ChoiceLoader(fs_loaders),
    enable_async=True,
)


default_templates = Environment(loader=fs_loaders[1], enable_async=True)


def sonarr() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings().sonarr_url.encoded_string().rstrip("/") + "/api/v3",
        headers={"X-Api-Key": settings().sonarr_api_key.get_secret_value()},
    )


def handle_sonarr_request_error(exception: httpx.HTTPError):
    match exception:
        case (
            httpx.ConnectError()
            | httpx.HTTPStatusError(response=httpx.Response(status_code=404))
        ):
            logger.critical(
                f"{settings().sonarr_url} couldn't be reached. Check TEREBII_SONARR_URL."
            )

        case httpx.HTTPStatusError():
            if exception.response.status_code == 401:
                logger.critical(
                    f"Invalid API key for {settings().sonarr_url}. Check TEREBII_SONARR_API_KEY."
                )
            else:
                logger.critical(
                    f"{settings().sonarr_url} responded with an HTTP {exception.response.status_code} "
                    f"status code."
                )

        case _:
            logger.critical(
                "There was a problem connecting to Sonarr. Check TEREBII_SONARR_URL and TEREBII_SONARR_API_KEY,"
                "and make sure your Sonarr instance is running and reachable from Terebii's container."
            )


async def render_default_template(template: str, context: dict) -> str:
    return await default_templates.get_template(template).render_async(context)


async def render_template(template_name: str, context: dict) -> str:
    try:
        return await templates.get_template(template_name).render_async(context)
    except jinja2.exceptions.TemplateError as e:
        logger.warning(
            f"There was an error rendering {template_name}. Falling back to the default template.\n"
            f"Jinja said: {e}"
        )

        return await render_default_template(template_name, context)
        