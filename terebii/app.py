from datetime import datetime
from pathlib import Path

import inflect as ifl
import pendulum
from apprise import Apprise
from jinja2 import ChoiceLoader, Environment, FileSystemLoader
from loguru import logger
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

inflect = ifl.engine()


@broker.task
async def send_notification(episode_id: int):
    logger.debug(f"Preparing to send notification for episode with ID {episode_id}")

    async with utils.sonarr() as sonarr:
        logger.debug(f"Retreiving episode with ID {episode_id}")

        resp = await sonarr.get(f"/calendar/{episode_id}")

        if resp.status_code == 404:
            logger.debug(
                f"Episode with ID {episode_id} not found. Maybe the show was deleted?"
            )
            return

        with logger.catch():
            resp.raise_for_status()

        episode = resp.json()

        logger.debug(f"Retrieved episode with ID {episode_id}")

    title = episode["title"]
    show_name = episode["series"]["title"]
    runtime = episode["runtime"]
    network = episode["series"]["network"]

    episode_num = episode["episodeNumber"]
    episode_num_00 = str(episode_num).zfill(2)
    episode_num_word = inflect.number_to_words(episode_num)
    episode_ordinal = inflect.ordinal(episode_num)
    episode_ordinal_word = inflect.number_to_words(episode_ordinal)
    season_num = episode["seasonNumber"]
    season_num_00 = str(season_num).zfill(2)
    season_num_word = inflect.number_to_words(season_num)
    season_ordinal = inflect.ordinal(season_num)
    season_ordinal_word = inflect.number_to_words(season_ordinal)

    air_date_utc = pendulum.parse(episode["airDateUtc"])
    air_date = air_date_utc.in_tz(settings().timezone)

    episode_log_str = (
        f"{show_name} S{season_num} E{episode_num} — {title} ({episode_id})"
    )

    if not (episode["monitored"] or settings().include_unmonitored):
        logger.debug(
            f"A notification was scheduled for {episode_log_str} but it is not monitored and "
            f"TEREBII_INCLUDE_UNMONITORED is False, so it is being skipped"
        )

        return

    variables = {
        "title": title,
        "show_name": show_name,
        "runtime": runtime,
        "network": network,
        "episode_num": episode_num,
        "episode_num_00": episode_num_00,
        "episode_ordinal": episode_ordinal,
        "episode_num_word": episode_num_word,
        "episode_ordinal_word": episode_ordinal_word,
        "season_num": season_num,
        "season_num_00": season_num_00,
        "season_ordinal": season_ordinal,
        "season_num_word": season_num_word,
        "season_ordinal_word": season_ordinal_word,
        "air_date": datetime.fromisoformat(air_date.to_iso8601_string()),
        "air_date_utc": datetime.fromisoformat(air_date_utc.to_iso8601_string()),
    }

    logger.debug(f"Rendering notification templates with variables: {variables}")

    notification_title = templates.get_template("title.jinja").render(variables)
    notification_body = templates.get_template("body.jinja").render(variables)

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
            logger.debug(f"Including poster with URL {poster}")
            attach = (poster,)

    notifier = Apprise()
    notifier.add(settings().notification_url.encoded_string())

    logger.info(f"Sending notification for {episode_log_str}")

    result = await notifier.async_notify(
        title=notification_title,
        body=notification_body,
        attach=attach,
    )

    if result:
        logger.debug(f"Notification successful: {episode_log_str}")
    else:
        logger.error(f"Notification failed: {episode_log_str}")


@broker.task(schedule=[{"interval": settings().refresh_interval}])
async def get_episodes():
    start = pendulum.now("UTC")
    end = start + pendulum.Duration(weeks=1)

    logger.debug(f"Airing window: {start} to {end}")

    async with utils.sonarr() as sonarr:
        logger.info(f"Retrieving calendar from {settings().sonarr_url}...")
        resp = await sonarr.get(
            "/calendar",
            params={
                "start": start.to_iso8601_string(),
                "end": end.to_iso8601_string(),
                "unmonitored": settings().include_unmonitored,
                "includeSeries": True,
            },
        )

        with logger.catch():
            resp.raise_for_status()

        episodes = resp.json()

        logger.info("Calendar retrieved!")

    await redis_source.startup()

    for episode in episodes:
        if air_date := episode.get("airDateUtc"):
            logger.debug(
                f"Adding notification for {episode['series']['title']} S{episode['seasonNumber']} "
                f"E{episode['episodeNumber']} — {episode['title']} at {air_date} UTC ({episode['id']})"
            )

            await (
                send_notification.kicker()
                .with_schedule_id(str(episode["id"]))
                .schedule_by_time(
                    source=redis_source,
                    time=air_date,
                    episode_id=episode["id"],
                )
            )
