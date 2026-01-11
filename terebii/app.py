import httpx
import inflect as ifl
import pendulum
from apprise import Apprise
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

backend = RedisAsyncResultBackend(
    settings().redis_url.get_secret_value().encoded_string()
)

broker = RedisStreamBroker(
    settings().redis_url.get_secret_value().encoded_string()
).with_result_backend(backend)

redis_source = ListRedisScheduleSource(
    settings().redis_url.get_secret_value().encoded_string()
)

scheduler = TaskiqScheduler(
    broker=broker,
    sources=[redis_source, LabelScheduleSource(broker)],
)

inflect = ifl.engine()


@broker.task
@logger.catch(httpx.HTTPError, onerror=utils.handle_sonarr_request_error)
async def send_notification(episode_id: int, exec_time: float):
    exec_time = pendulum.from_timestamp(exec_time)
    task_age = pendulum.now().diff(exec_time)

    logger.debug(
        f"Notification task for episode with ID {episode_id} is {task_age.seconds} seconds old; scheduled for "
        f"{utils.get_date_with_tz_log_str(exec_time)}"
    )

    if task_age.minutes > 2:
        logger.debug(
            f"Notification task for episode with ID {episode_id} is too old (≥2 minutes); skipping"
        )
        return

    logger.debug(f"Preparing to send notification for episode with ID {episode_id}")

    async with utils.sonarr() as sonarr:
        logger.debug(f"Retreiving episode with ID {episode_id}")

        resp = await sonarr.get(f"/calendar/{episode_id}")

        if resp.status_code == 404:
            logger.debug(
                f"Episode with ID {episode_id} not found. Maybe the show was deleted?"
            )
            return

        resp.raise_for_status()

        episode = resp.json()
        episode_log_str = utils.get_episode_log_str(episode)

        logger.debug(f"Retrieved {episode_log_str}")

    if not (episode["monitored"] or settings().include_unmonitored):
        logger.info(f"{episode_log_str} is unmonitored; skipping notification")
        return

    template_variables = utils.get_episode_template_variables(episode)

    logger.debug(
        f"Rendering notification templates for {episode_log_str} with variables: {template_variables}"
    )

    notification_title = await utils.render_template("title.jinja", template_variables)
    notification_body = await utils.render_template("body.jinja", template_variables)

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
            logger.debug(f"Including poster with URL {poster} for {episode_log_str}")
            attach = (poster,)
        else:
            logger.debug(f"No poster found for {episode_log_str}")

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
@logger.catch(httpx.HTTPError, onerror=utils.handle_sonarr_request_error)
async def get_episodes():
    start = pendulum.now("UTC")
    end = start.add(hours=24)

    logger.debug(
        f"Looking for episodes airing within 24 hours ({start.to_rfc3339_string()} to {end.to_rfc3339_string()})"
    )

    async with utils.sonarr() as sonarr:
        logger.debug(f"Retrieving calendar from {settings().sonarr_url}...")

        resp = await sonarr.get(
            "/calendar",
            params={
                "start": start.to_rfc3339_string(),
                "end": end.to_rfc3339_string(),
                "unmonitored": settings().include_unmonitored,
                "includeSeries": True,
            },
        )

        resp.raise_for_status()

        episodes = resp.json()

        logger.debug(f"Calendar retrieved from {settings().sonarr_url}")

        logger.info(
            f"Found {len(episodes)} {inflect.plural('episode', len(episodes))} "
            f"airing within 24 hours ({start.to_rfc3339_string()} to {end.to_rfc3339_string()})"
        )

    for episode in episodes:
        episode_log_str = utils.get_episode_log_str(episode)

        if settings().premieres_only and episode["episodeNumber"] != 1:
            logger.debug(f"{episode_log_str} is not a season premiere; skipping")
            continue

        if air_date_utc := episode.get("airDateUtc"):
            air_date_utc = pendulum.parse(air_date_utc)

            logger.debug(
                f"Scheduling notification for {episode_log_str} "
                f"at {utils.get_date_with_tz_log_str(air_date_utc)}"
            )

            await (
                send_notification.kicker()
                .with_schedule_id(str(episode["id"]))
                .schedule_by_time(
                    source=redis_source,
                    time=air_date_utc,
                    episode_id=episode["id"],
                    exec_time=air_date_utc.float_timestamp,
                )
            )
