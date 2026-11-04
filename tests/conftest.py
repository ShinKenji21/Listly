"""Shared test setup.

No test ever calls the real Meta API: `fake_api` swaps in a fake server that returns the replies a
test queues up and records every request, so tests are free, fast and run without a key.
"""

import json
import os
from pathlib import Path

# Set before listly is imported: real (non-demo) code paths, with a dummy key.
os.environ["LISTLY_DEMO"] = "0"
os.environ["META_API_KEY"] = "test-key"

import httpx2 as httpx  # the HTTP library the openai SDK uses  # noqa: E402
import openai  # noqa: E402
import pytest  # noqa: E402

from listly import cache, storage  # noqa: E402
from listly.ai import api  # noqa: E402
from listly.config import BASE_URL  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def isolated_files(tmp_path, monkeypatch):
    """Every test gets its own empty cache and data folders, never the seller's real ones."""
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(storage, "OLD_DIR", tmp_path / "old-listings")


class FakeAPI:
    """Stands in for https://api.meta.ai/v1/responses."""

    def __init__(self):
        self.replies = []  # queued outputs, used in order
        self.requests = []  # the JSON body of every request sent

    def reply_text(self, *texts: str) -> None:
        """Queue plain text replies (like the model's JSON answer)."""
        for text in texts:
            self.replies.append([{"type": "message", "id": "m", "role": "assistant", "status": "completed",
                                  "content": [{"type": "output_text", "text": text, "annotations": []}]}])

    def reply_json(self, *objects: dict) -> None:
        self.reply_text(*(json.dumps(o) for o in objects))

    def reply_output(self, output: list) -> None:
        """Queue a raw output list (for image results, search results, citations...)."""
        self.replies.append(output)

    def _handle(self, request):
        body = json.loads(request.content)
        self.requests.append(body)
        output = self.replies.pop(0)
        return httpx.Response(200, json={
            "id": "resp_test", "object": "response", "created_at": 0, "model": body["model"],
            "status": "completed", "output": output, "parallel_tool_calls": False, "tool_choice": "auto", "tools": [],
        })


@pytest.fixture
def fake_api(monkeypatch):
    fake = FakeAPI()
    client = openai.OpenAI(api_key="test-key", base_url=BASE_URL, http_client=httpx.Client(transport=httpx.MockTransport(fake._handle)))
    monkeypatch.setattr(api, "get_client", lambda: client)
    return fake
