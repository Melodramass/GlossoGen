"""The models and providers a run can be launched with.

The hosted entries are the models the run and evaluation pickers offer. Self-hosted
models are discovered from the ``SELF_HOSTED_BASE_URLS`` environment variable (a
JSON object mapping model name → endpoint URL), so adding a self-hosted deployment
needs no code change here. Prices live elsewhere: see ``token_pricing``.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

SELF_HOSTED_PROVIDER = "self-hosted"


# (model, provider) pairs offered for hosted APIs. Model names use dashes, matching
# the IDs the APIs accept.
_HOSTED_MODELS: tuple[tuple[str, str], ...] = (
    ("claude-opus-4-7", "anthropic"),
    ("claude-opus-4-6", "anthropic"),
    ("claude-opus-4-5", "anthropic"),
    ("claude-sonnet-4-6", "anthropic"),
    ("claude-haiku-4-5", "anthropic"),
    ("gpt-5.4-nano", "openai"),
    ("gpt-5.4-mini", "openai"),
    ("gpt-5.4", "openai"),
    ("gpt-5.2", "openai"),
)


def _get_self_hosted_model_names() -> list[str]:
    """Return model names listed in the ``SELF_HOSTED_BASE_URLS`` env var.

    Returns an empty list when the env var is unset, empty, or not valid JSON,
    so that environments without a self-hosted endpoint do not raise.
    """
    raw = os.environ.get("SELF_HOSTED_BASE_URLS", "")
    if not raw:
        return []
    try:
        parsed: dict[str, str] = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("SELF_HOSTED_BASE_URLS is not valid JSON; ignoring.")
        return []
    return list(parsed.keys())


def list_providers() -> list[str]:
    """Return unique provider names, including ``self-hosted`` if any are configured.

    The order is: providers of the hosted models (in listing order), then
    ``self-hosted`` last when ``SELF_HOSTED_BASE_URLS`` lists at least one model.
    """
    seen: set[str] = set()
    providers: list[str] = []
    for _, provider in _HOSTED_MODELS:
        if provider not in seen:
            seen.add(provider)
            providers.append(provider)
    if _get_self_hosted_model_names():
        providers.append(SELF_HOSTED_PROVIDER)
    return providers


def list_models() -> list[tuple[str, str]]:
    """Return every offered (model, provider) pair.

    The hosted models come first, followed by every model listed in
    ``SELF_HOSTED_BASE_URLS``.
    """
    self_hosted = [(name, SELF_HOSTED_PROVIDER) for name in _get_self_hosted_model_names()]
    return list(_HOSTED_MODELS) + self_hosted
