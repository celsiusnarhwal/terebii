from pathlib import Path

import httpx
import inflect as ifl
import jinja2
import pendulum
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

inflect = ifl.engine()


def sonarr() -> httpx.AsyncClient:
    headers = settings().sonarr_headers.get_secret_value()
    params = {}

    if settings().sonarr_api_key_in_url:
        params["apikey"] = settings().sonarr_api_key.get_secret_value()
    else:
        headers["x-api-key"] = settings().sonarr_api_key.get_secret_value()

    auth = (
        httpx.BasicAuth(
            settings().sonarr_username, settings().sonarr_password.get_secret_value()
        )
        if settings().sonarr_username and settings().sonarr_password
        else None
    )

    return httpx.AsyncClient(
        base_url=settings().sonarr_url.encoded_string().rstrip("/") + "/api/v3",
        headers=headers,
        params=params,
        auth=auth,
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
                    f"{settings().sonarr_url} is rejecting requests from Terebii. Check TEREBII_SONARR_API_KEY and, "
                    f"if necessary, TEREBII_SONARR_USERNAME and TEREBII_SONARR_PASSWORD."
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


def get_episode_log_str(episode: dict) -> str:
    return (
        f"{episode['series']['title']} S{episode['seasonNumber']} E{episode['episodeNumber']} — {episode['title']} "
        f"({episode['id']})"
    )


def get_date_with_tz_log_str(date: pendulum.DateTime) -> str:
    log_str = date.to_rfc3339_string()

    if not pendulum.now(settings().timezone).is_utc():
        log_str += f" ({settings().timezone}: {date.in_timezone(settings().timezone).to_rfc3339_string()})"

    return log_str


def get_episode_template_variables(episode: dict) -> dict:
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

    tvdb_url = (
        f"https://thetvdb.com/?tab=series&id={tvdb_id}"
        if (tvdb_id := episode["series"]["tvdbId"])
        else None
    )
    tmdb_url = (
        f"https://themoviedb.org/tv/{tmdb_id}"
        if (tmdb_id := episode["series"]["tmdbId"])
        else None
    )
    imdb_url = (
        f"https://imdb.com/title/{imdb_id}"
        if (imdb_id := episode["series"]["imdbId"])
        else None
    )

    air_date_utc = pendulum.parse(episode["airDateUtc"])
    air_date = air_date_utc.in_timezone(settings().timezone)
    air_date_timestamp = air_date_utc.int_timestamp

    return {
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
        "air_date_timestamp": air_date_timestamp,
    }


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
