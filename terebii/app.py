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
async def send_notification(episode_id: int, air_date_utc: str):
    air_date_utc = pendulum.parse(air_date_utc)
    task_age = pendulum.now().diff(air_date_utc)

    logger.debug(
        f"Notification task for episode with ID {episode_id} is {task_age.seconds} seconds old "
        f"(scheduled for {air_date_utc})"
    )

    if task_age.minutes > 2:
        logger.debug(
            f"Notification task for episode with ID {episode_id} is too old; skipping"
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

    air_date = air_date_utc.in_tz(settings().timezone)

    if tvdb_id := episode["series"]["tvdbId"]:
        tvdb_url = f"https://thetvdb.com/?tab=series&id={tvdb_id}"
    else:
        tvdb_url = None

    if tmdb_id := episode["series"]["tmdbId"]:
        tmdb_url = f"https://themoviedb.com/tv/{tmdb_id}"
    else:
        tmdb_url = None

    if imdb_id := episode["series"]["imdbId"]:
        imdb_url = f"https://imdb.com/title/{imdb_id}"
    else:
        imdb_url = None

    episode_log_str = (
        f"{show_name} S{season_num} E{episode_num} — {title} ({episode_id})"
    )

    if not (episode["monitored"] or settings().include_unmonitored):
        logger.info(f"{episode_log_str} is unmonitored; skipping notification")

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
        "tvdb_url": tvdb_url,
        "tmdb_url": tmdb_url,
        "imdb_url": imdb_url,
        "air_date": air_date,
        "air_date_utc": air_date_utc,
    }

    logger.debug(
        f"Rendering notification templates for {episode_log_str} with variables: {variables}"
    )

    notification_title = await utils.render_template("title.jinja", variables)
    notification_body = await utils.render_template("body.jinja", variables)

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

    logger.debug(f"Looking for episodes airing within 24 hours ({start} to {end})")

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
            f"Scheduling notifications for {len(episodes)} episodes airing within 24 hours ({start} to {end})"
        )

    for episode in episodes:
        if air_date_utc := episode.get("airDateUtc"):
            logger.debug(
                f"Scheduling notification for {episode['series']['title']} S{episode['seasonNumber']} "
                f"E{episode['episodeNumber']} — {episode['title']} at {air_date_utc} ({episode['id']})"
            )

            await (
                send_notification.kicker()
                .with_schedule_id(str(episode["id"]))
                .schedule_by_time(
                    source=redis_source,
                    time=air_date_utc,
                    episode_id=episode["id"],
                    air_date_utc=air_date_utc,
                )
            )
