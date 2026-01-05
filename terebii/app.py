from datetime import datetime
from pathlib import Path

import pendulum
from apprise import Apprise
from jinja2 import ChoiceLoader, Environment, FileSystemLoader
from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import (
    ListRedisScheduleSource,
    RedisAsyncResultBackend,
    RedisStreamBroker,
)

from terebii import utils
from terebii.settings import settings

backend = RedisAsyncResultBackend(redis_url=settings().redis_url.encoded_string())

broker = RedisStreamBroker(
    url=settings().redis_url.encoded_string()
).with_result_backend(backend)

redis_source = ListRedisScheduleSource(settings().redis_url.encoded_string())

scheduler = TaskiqScheduler(
    broker=broker, sources=[redis_source, LabelScheduleSource(broker)]
)

template_loader = ChoiceLoader(
    [
        FileSystemLoader(Path(__file__).parent / "templates"),
        FileSystemLoader(Path(__file__).parent / "default_templates"),
    ]
)

templates = Environment(loader=template_loader)


@broker.task
async def send_notification(episode_id: int):
    async with utils.sonarr() as sonarr:
        resp = await sonarr.get(f"/calendar/{episode_id}")

        if resp.status_code == 404:
            return

        resp.raise_for_status()
        episode = resp.json()

    title = episode["title"]
    show_name = episode["series"]["title"]
    runtime = episode["runtime"]
    network = episode["series"]["network"]

    episode_num = episode["episodeNumber"]
    episode_num00 = str(episode_num).zfill(2)
    season_num = episode["seasonNumber"]
    season_num00 = str(season_num).zfill(2)

    air_date_local = pendulum.parse(episode["airDate"])
    air_date_utc = pendulum.parse(episode["airDateUtc"])

    variables = {
        "title": title,
        "show_name": show_name,
        "runtime": runtime,
        "network": network,
        "episode_num": episode_num,
        "episode_num00": episode_num00,
        "season_num": season_num,
        "season_num00": season_num00,
        "air_date": datetime.fromisoformat(air_date_local.to_iso8601_string()),
        "air_date_utc": datetime.fromisoformat(air_date_utc.to_iso8601_string()),
    }

    notification_title = templates.get_template("title.jinja").render(variables)
    notification_body = templates.get_template("body.jinja").render(variables)

    notifier = Apprise()
    notifier.add(settings().notification_url.encoded_string())

    attach = None

    if settings().include_posters:
        poster = next(
            (
                image["remoteUrl"]
                for image in episode["series"]["images"]
                if image["coverType"] == "poster"
            ),
            None,
        )

        if poster:
            attach = (poster,)

    await notifier.async_notify(
        title=notification_title,
        body=notification_body,
        attach=attach,
    )


@broker.task(schedule=[{"interval": settings().refresh_interval}])
async def get_episodes():
    start = pendulum.now("UTC")
    end = start + pendulum.Duration(weeks=1)

    async with utils.sonarr() as sonarr:
        resp = await sonarr.get(
            "/calendar",
            params={"start": start.to_iso8601_string(), "end": end.to_iso8601_string()},
        )

        resp.raise_for_status()
        episodes = resp.json()

    await redis_source.startup()

    for episode in episodes:
        if air_date := episode.get("airDateUtc"):
            await send_notification.schedule_by_time(
                source=redis_source,
                time=pendulum.parse(air_date),
                episode_id=episode["id"],
                task_id=str(episode["id"]),
            )
