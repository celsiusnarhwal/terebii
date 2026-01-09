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
