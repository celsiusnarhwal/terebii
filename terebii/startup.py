#!/usr/bin/env -S uv run --directory /app/

import importlib.metadata

import pendulum
import rich
import uvloop

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


if __name__ == "__main__":
    uvloop.run(startup())
