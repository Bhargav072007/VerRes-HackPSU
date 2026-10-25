import httpx
import pytest

from api.app.providers.http import Gateway
from api.app.providers.metadata import OpenAlex, normalize_openalex_id


@pytest.mark.parametrize("identifier", ["W1", "https://openalex.org/W1"])
@pytest.mark.parametrize("flag", [False, True, None, "false", 0])
async def test_openalex_work_id_uses_a_single_cached_lookup(identifier, flag):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200, json={"id": "https://openalex.org/W1", "title": "Test", "is_retracted": flag}
        )

    async with Gateway(transport=httpx.MockTransport(handler), attempts=1) as gateway:
        alex = OpenAlex(gateway)
        for _ in range(2):
            result = await alex.lookup(identifier)
            assert result.definitive
            assert result.works[0].is_retracted is (flag if type(flag) is bool else None)
    assert len(requests) == 1 and requests[0].url.path == "/works/W1"


@pytest.mark.parametrize(
    "value",
    [None, "W0", "W1/extra", "https://evil.example/W1", "https://openalex.org/W1?key=secret"],
)
def test_invalid_openalex_ids_are_not_receipts(value):
    assert normalize_openalex_id(value) is None
