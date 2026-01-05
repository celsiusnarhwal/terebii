# Terebii ([テレビィ](https://en.wiktionary.org/wiki/テレビ))

Terebii is an airing notification service for [Sonarr](https://sonarr.tv). When new episodes of your shows are airing,
Terebii can notify you through any service supported by [Apprise](https://github.com/caronc/apprise), including
Pushover, ntfy, Discord, IFTTT, and [many, many, more](https://github.com/caronc/apprise/wiki).

## Installation

[Docker](https://docs.docker.com) is the only supported way of running Terebii. You must set the 
`TEREBII_SONARR_URL`, `TEREBII_SONAR_API_KEY`, and `TEREBII_NOTIFICATION_URL` environment variables; 
see [Configuration](#configuration).

In the below examples, `{TEREBII_TEMPLATE_DIR}` is a placeholder for a path on your machine where Terebii will look 
for notification templates (see [Customizing Notifications](#customizing-notifications)). If you don't intend to 
customize Terebii's notifications, you don't need to mount this directory.

<hr>

<details>
<summary>Supported tags</summary>
<br>

| **Name**             | **Description**                                                                             | **Example**                                                                        |
|----------------------|---------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------|
| `latest`             | The latest stable version of Terebii.                                                       | `ghcr.io/celsiusnarhwal/terebii:latest`                                            |
| Major version number | The latest release of this major version of Terebii. May be optionally prefixed with a `v`. | `ghcr.io/celsiusnarhwal/terebii:1`<br/>`ghcr.io/celsiusnarhwal/terebii:v1`         |
| Minor version number | The latest release of this minor version of Terebii. May be optionally prefixed with a `v`. | `ghcr.io/celsiusnarhwal/terebii:1.0`<br/>`ghcr.io/celsiusnarhwal/terebii:v1.0`     |
| Exact version number | This version of Terebii exactly. May be optionally prefixed with a `v`.                     | `ghcr.io/celsiusnarhwal/terebii:1.0.0`<br/>`ghcr.io/celsiusnarhwal/terebii:v1.0.0` |
| `edge`               | The latest commit to Terebii's `main` branch. Unstable.                                     | `ghcr.io/celsiusnarhwal/terebii:edge`                                              |                                                                                             |                                                                                    |

All Terebii images are distributed both with and without a Redis server. If you would prefer an image without one,
append `-noredis` to the tag of your choice.[^3]

</details>

<hr>

### Docker Compose

```yaml
services:
  snowflake:
    image: ghcr.io/celsiusnarhwal/terebii:latest
    container_name: terebii
    restart: unless-stopped
    environment:
      - TEREBII_SONARR_URL=sonarr.example.com
      - TEREBII_SONARR_API_KEY=your-sonarr-api-key
      - TEREBI_NOTIFICATION_URL=some://apprise.url
    volumes:
      - {TEREBII_TEMPLATE_DIR}:/app/terebii/templates
```

### Docker CLI

```shell
docker run -d \
  --name terebii \
  --restart unless-stopped \
  -e TEREBII_SONARR_URL=sonarr.example.com \
  -e TEREBII_SONARR_API_KEY=your-sonarr-api-key \
  -e TEREBI_NOTIFICATION_URL=some://apprise.url \
  -v {TEREBII_TEMPLATE_DIR}:/app/terebii/templates \
  ghcr.io/celsiusnarhwal/terebii:latest
```

## Customizing Notifications

You can customize the content of Terebii's notifications by creating [Jinja](https://jinja.palletsprojects.com/en/stable/)
templates in `TEREBII_TEMPLATE_DIR`. Notification titles can be customized by creating a template named
`title.jinja`; notification bodies can be customized by creating a template named `body.jinja`.

For example:

<details>
<summary><code>title.jinja</code></summary>
<br>

The following template:

```
{{ show_name }} is Airing
```

will result in a notification title similar to this:

> Sound! Euphonium is Airing

</details>

<details>
<summary><code>body.jinja</code></summary>
<br>

The following template:
<br>
```
S{{ season_num }} E{{ episode_num }} — {{ title }} is now airing on {{ network }}.
```

will result in a notification body similar to this:

> S1 E8 — Festival Triangle is now airing on NHK Educational TV.

</details>

The above examples are also the default values for each template if either one is not present.

The following variables are provided to notification templates.

| **Variable**    | **Type**                                                                                       | **Description**                                                                                      |
|-----------------|------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------|
| `title`         | String ([`str`](https://docs.python.org/3/library/stdtypes.html#str))                          | The title of the episode.                                                                            |
| `show_name`     | String ([`str`](https://docs.python.org/3/library/stdtypes.html#str))                          | The name of the show.                                                                                |
| `runtime`       | Integer ([`int`](https://docs.python.org/3/library/functions.html#int))                        | The runtime of the episode in minutes, rounded down to the nearest minute.                           |
| `network`       | String ([`str`](https://docs.python.org/3/library/stdtypes.html#str))                          | The network the show airs on.                                                                        |
| `episode_num`   | Integer ([`int`](https://docs.python.org/3/library/functions.html#int))                        | The episode number (e.g., `8`).                                                                      |
| `episode_num00` | String ([`str`](https://docs.python.org/3/library/stdtypes.html#str))                          | The two-digit episode number (e.g. `08`). Note that unlike `episode_num`, this variable is a string. |
| `season_num`    | Integer ([`int`](https://docs.python.org/3/library/functions.html#int))                        | The season number (e.g., `1`).                                                                       |
| `season_num00`  | String ([`str`](https://docs.python.org/3/library/stdtypes.html#str))                          | The two-digit season number (e.g. `01`). Note that unlike `season_num`, this variable is a string.   |                                                                         |                                                                                                     |
| `air_date`      | Date ([`datetime.datetime`](https://docs.python.org/3/library/datetime.html#datetime-objects)) | The air date of the episode in the time zone of the connected Sonarr instance.                       |
| `air_date_utc`  | Date ([`datetime.datetime`](https://docs.python.org/3/library/datetime.html#datetime-objects)) | The air date of the episode in UTC.                                                                  |                                                                                               |                                                                                                      |

All template variables are [Python](https://python.org) objects and can be manipulated within notification templates
in all of the ways that Jinja supports.

### Formatting dates

The `air_date` and `air_date_utc` variables can be formatted using [`strftime()`](https://docs.python.org/3/library/datetime.html#datetime.date.strftime), e.g.,

```
{{ air_date.strftime("%Y-%m-%d %H:%M:%S") }}
```

For all format codes, see [strftime.org](https://strftime.org).

## Configuration

Terebii can be configured via the following environment variables:

| **Variable**               | **Type** | **Description**                                                                                                                                                                                                                                                                                                         | **Required?** | **Default (if not required)** |
|----------------------------|----------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------|-------------------------------|
| `TEREBII_SONARR_URL`       | String   | The URL of a Sonarr instance.                                                                                                                                                                                                                                                                                           | Yes           |                               |
| `TEREBII_SONARR_API_KEY`   | String   | The API key for the Sonarr instance reachable at `TEREBII_SONARR_URL`.                                                                                                                                                                                                                                                  | Yes           |                               |
| `TEREBII_NOTIFICATION_URL` | String   | An [Apprise URL](https://github.com/caronc/apprise/wiki/URLBasics) for Terebii to send notifications to.                                                                                                                                                                                                                | Yes           |                               |
| `TEREBII_REFRESH_INTERVAL` | String   | A [Go duration string](https://pkg.go.dev/time#ParseDuration) representing the interval at which Terebii should pull new episodes from Sonarr's calendar. In addition to the standard Go units, you can use `d` for day, `w` for week, `mm` for month, and `y` for year.[^1] Must be greater than or equal to 1 second. | No            | `1m`                          |
| `TEREBII_INCLUDE_POSTERS`  | Boolean  | Whether to include show posters as notification attachments when possible.[^2]                                                                                                                                                                                                                                          | No            | `false`                       |
| `TEREBII_REDIS_URL`        | String   | The URL of a Redis instance. If specified, Terebii will use this Redis instance instead of its integrated one. Must begin with `redis://` or `rediss://`.                                                                                                                                                               | No[^3]        | `redis://localhost`           |

[^1]: 1 day = 24 hours, 1 week = 7 days, 1 month = 30 days, and 1 year = 365 days.
[^2]: "Possible" meaning that a poster can be found for the show and the notification service supports attachments.
[^3]: If you're using a Redis-less Terebii image, `TEREBII_REDIS_URL` is required.