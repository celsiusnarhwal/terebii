import httpx

from terebii.settings import settings


def sonarr() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings().sonarr_url.encoded_string().rstrip("/") + "/api/v3",
        headers={"X-Api-Key": settings().sonarr_api_key.get_secret_value()},
    )
