"""Thin wrapper around OpenAI / xAI chat that always returns parsed JSON and logs cost."""
import base64
import json
from pathlib import Path

from openai import OpenAI

from . import budget, config


def openai_client() -> OpenAI:
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing. Add it to the .env file.")
    return OpenAI(api_key=config.OPENAI_API_KEY)


def xai_client() -> OpenAI:
    if not config.XAI_API_KEY:
        raise RuntimeError("XAI_API_KEY is missing. Add it to the .env file.")
    return OpenAI(api_key=config.XAI_API_KEY, base_url="https://api.x.ai/v1")


def _chat_client() -> OpenAI:
    return xai_client() if config.LLM_PROVIDER == "xai" else openai_client()


def image_data_uri(path: str | Path) -> str:
    p = Path(path)
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


def chat_json(system: str, user: str, images: list | None = None, max_out: int = 6000,
              what: str = "chat") -> dict:
    """Ask the model for a JSON object. `images` = list of local image paths (sent at low detail)."""
    model = config.LLM_MODEL
    est_in = (len(system) + len(user)) // 3 + 100 * len(images or [])
    budget.guard(budget.chat_cost(model, est_in, max_out), what)

    content: list | str = user
    if images:
        content = [{"type": "text", "text": user}] + [
            {"type": "image_url", "image_url": {"url": image_data_uri(p), "detail": "low"}}
            for p in images
        ]

    kwargs = dict(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
        response_format={"type": "json_object"},
    )
    is_reasoning = config.LLM_PROVIDER == "openai" and model.startswith(("gpt-5", "o1", "o3", "o4"))
    if is_reasoning:
        kwargs["reasoning_effort"] = config.LLM_REASONING_EFFORT
        kwargs["max_completion_tokens"] = max_out
    else:
        kwargs["max_tokens"] = max_out
        kwargs["temperature"] = 0.9

    resp = _chat_client().chat.completions.create(**kwargs)
    u = resp.usage
    cost = budget.chat_cost(model, u.prompt_tokens, u.completion_tokens) if u else budget.chat_cost(model, est_in, max_out)
    budget.record("chat", model, cost, what)

    text = resp.choices[0].message.content or ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise RuntimeError(f"Model did not return JSON for '{what}'. Output was: {text[:500]}")
