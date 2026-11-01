"""One place to call the Meta Model API, so every step handles errors the same way."""

import json

import openai

from listly.config import get_client


class StepError(Exception):
    """A step failed. The message is safe to show the seller."""


def create_response(label: str, **kwargs):
    """Call the Responses API (/v1/responses). `label` names the model in error messages."""
    try:
        return get_client().responses.create(**kwargs)
    # Don't show the raw SDK error: auth errors can echo part of the API key.
    except openai.AuthenticationError:
        raise StepError("The API key was rejected. Check META_API_KEY in your .env file.")
    except openai.RateLimitError:
        raise StepError("Too many requests or out of credits. Wait a moment and try again.")
    except openai.APIError as e:
        raise StepError(f"Couldn't reach {label} ({type(e).__name__}). Try again.")


def parse_json(text: str) -> dict:
    """Pull the JSON object out of the model's reply (models sometimes add text or ``` fences)."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in reply")
    return json.loads(text[start : end + 1])
