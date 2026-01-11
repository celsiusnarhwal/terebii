#!/usr/bin/env -S uv run --directory /app/

import importlib.metadata

import pendulum
import rich
import uvloop
from apprise import Apprise
from loguru import logger

from terebii import utils
from terebii.settings import settings


async def startup():
    version = importlib.metadata.version("terebii")

    if version == "0.0.0":
        version = "Edge"

    variables = {
        "version": version,
        "year": pendulum.now(settings().timezone).year,
    }

    rich.print(
        "\n" + await utils.render_default_template("startup.jinja", variables) + "\n"
    )

    if settings().test_notification:
        logger.debug("Sending test notification")

        notifier = Apprise()
        notifier.add(str(settings().notification_url))

        result = notifier.async_notify(
            title="Hello from Terebii",
            body="This is a test notification from Terebii.\n"
            "https://github.com/celsiusnarhwal/terebii",
        )

        if result:
            logger.debug("Test notification successful")
        else:
            logger.error("Test notification failed")


if __name__ == "__main__":
    uvloop.run(startup())
