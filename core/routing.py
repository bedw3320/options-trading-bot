from __future__ import annotations

from pydantic_ai.exceptions import UserError
from pydantic_ai.models import infer_model

from utils.logging import get_logger

log = get_logger(__name__)

# model format: "provider:model"
MODEL = "anthropic:claude-3-5-haiku-latest"


def build_model(*, strict: bool = True):
    try:
        model = infer_model(MODEL)
        log.info("Built model: %s", MODEL)
        return model
    except (UserError, ValueError, ImportError) as e:
        msg = f"Failed to build model '{MODEL}': {e}"
        if strict:
            raise ValueError(msg) from e
        log.warning(msg)
        return None
