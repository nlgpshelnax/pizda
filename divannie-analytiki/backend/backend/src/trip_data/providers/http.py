"""HTTP mapping for future adapters; caller owns the AsyncClient and credentials."""

import httpx

from trip_data.providers.base import ProviderFailure


async def request_json(client, method, url, *, params=None, headers=None, data=None, timeout=5):
    try:
        response = await client.request(
            method,
            url,
            params=params,
            headers=headers,
            json=data,
            timeout=httpx.Timeout(timeout, connect=3),
        )
    except httpx.TimeoutException as exc:
        raise ProviderFailure("timeout") from exc
    except httpx.RequestError as exc:
        raise ProviderFailure("unavailable") from exc
    if response.status_code in (401, 403):
        raise ProviderFailure("unauthorized")
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        try:
            seconds = max(0, float(retry_after)) if retry_after is not None else None
        except ValueError:
            seconds = None
        raise ProviderFailure("rate_limited", retry_after_seconds=seconds)
    if response.status_code >= 500:
        raise ProviderFailure("unavailable")
    if response.status_code >= 300:
        raise ProviderFailure("invalid_response")
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderFailure("invalid_response") from exc


async def get_json(client, url, *, params=None, headers=None, timeout=5):
    return await request_json(client, "GET", url, params=params, headers=headers, timeout=timeout)


async def post_json(client, url, *, data=None, headers=None):
    return await request_json(client, "POST", url, data=data, headers=headers)
