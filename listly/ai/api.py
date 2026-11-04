"""One place to call the Meta Model API, so every step handles errors the same way."""

import json
import time

import openai

from listly.config import get_client


class StepError(Exception):
    """A step failed. The message is safe to show the seller."""


def create_response(label: str, **kwargs):
    """Call the Responses API (/v1/responses). `label` names the model in error messages."""
    start = time.perf_counter()
    try:
        response = get_client().responses.create(**kwargs)
        # Printed to the terminal only, so we can see which model makes the app feel slow.
        print(f"[listly] {kwargs.get('model')} answered in {time.perf_counter() - start:.1f}s", flush=True)
        return response
    # Don't pass on the raw SDK error: auth errors can echo part of the API key.
    # "from None" also keeps it out of the traceback, so it can't leak into logs either.
    except openai.AuthenticationError:
        raise StepError("The API key was rejected. Check META_API_KEY in your .env file.") from None
    except openai.RateLimitError:
        raise StepError("Too many requests or out of credits. Wait a moment and try again.") from None
    except openai.APIError as e:
        raise StepError(f"Couldn't reach {label} ({type(e).__name__}). Try again.") from None


def parse_json(text: str) -> dict:
    """Pull the JSON object out of the model's reply (models sometimes add text or ``` fences)."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in reply")
    return json.loads(text[start : end + 1])
