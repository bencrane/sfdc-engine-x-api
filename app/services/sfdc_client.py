import httpx

_client: httpx.AsyncClient | None = None


async def init_sfdc_client() -> httpx.AsyncClient:
    global _client
    _client = httpx.AsyncClient(timeout=30.0)
    return _client


async def close_sfdc_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_sfdc_client() -> httpx.AsyncClient:
    if _client is None:
        raise RuntimeError("SFDC HTTP client not initialized. Is the app lifespan running?")
    return _client
