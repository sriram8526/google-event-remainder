import asyncio
import json

import httpx
import pytest

from app.ai import GeminiTextGenerator, NullTextGenerator
from app.config import Settings


def _gemini_reply(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def _generator(handler, **kwargs):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GeminiTextGenerator("secret-key", "test-model", 5, client=client, **kwargs)


def test_key_travels_in_a_header_and_body_has_system_instruction():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(
            url=str(request.url),
            key=request.headers.get("x-goog-api-key"),
            body=json.loads(request.content),
        )
        return httpx.Response(200, json=_gemini_reply("{}"))

    assert asyncio.run(_generator(handler).generate("SYS", "USER", 0.3)) == "{}"
    assert seen["key"] == "secret-key" and "secret-key" not in seen["url"]
    assert seen["body"]["systemInstruction"]["parts"][0]["text"] == "SYS"
    assert seen["body"]["generationConfig"]["temperature"] == 0.3


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(200, json={"candidates": []}),
        httpx.Response(200, json=_gemini_reply(123)),
        httpx.Response(200, text="not json"),
    ],
)
def test_any_failure_returns_none(response):
    assert asyncio.run(_generator(lambda _: response).generate("s", "u", 0.5)) is None


def test_network_error_returns_none():
    def boom(_):
        raise httpx.ConnectError("down")

    assert asyncio.run(_generator(boom).generate("s", "u", 0.5)) is None


def test_saturated_generator_sheds_load_instead_of_queueing():
    gate = asyncio.Event()

    async def handler(_):
        await gate.wait()
        return httpx.Response(200, json=_gemini_reply("{}"))

    async def scenario():
        generator = _generator(handler, max_concurrent=1)
        first = asyncio.create_task(generator.generate("s", "u", 0.5))
        await asyncio.sleep(0.05)
        shed = await generator.generate("s", "u", 0.5)
        gate.set()
        return shed, await first

    shed, first = asyncio.run(scenario())
    assert shed is None and first == "{}"


def test_null_generator_declines():
    assert asyncio.run(NullTextGenerator().generate("s", "u", 0.5)) is None


def test_settings_repr_hides_api_key():
    assert "super-secret" not in repr(Settings(gemini_api_key="super-secret"))


def test_settings_from_env_reads_overrides():
    settings = Settings.from_env(
        {"GEMINI_API_KEY": "k", "TRUSTED_PROXY_HOPS": "1", "RATE_LIMIT_REQUESTS": "5"}
    )
    assert (
        settings.gemini_api_key == "k"
        and settings.trusted_proxy_hops == 1
        and settings.rate_limit_requests == 5
    )


def test_aclose_releases_the_client():
    generator = _generator(lambda _: httpx.Response(200))
    asyncio.run(generator.aclose())
    assert generator._client.is_closed
