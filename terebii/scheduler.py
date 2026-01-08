import importlib.metadata
from pathlib import Path

import pendulum
import rich
from jinja2 import Environment, FileSystemLoader
from taskiq import TaskiqScheduler

from terebii.settings import settings

templates = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "default_templates")
)


class Scheduler(TaskiqScheduler):
    async def startup(self) -> None:
        version = importlib.metadata.version("terebii")

        if version == "0.0.0":
            version = "edge"

        variables = {
            "version": version,
            "year": pendulum.now(settings().timezone).year,
        }

        rich.print(
            "\n" + templates.get_template("startup.jinja").render(variables) + "\n"
        )
