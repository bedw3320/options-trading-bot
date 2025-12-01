from __future__ import annotations

import json
import os
from typing import Any


def load_state(path: str = "state.json") -> dict[str, Any]:
    if not os.path.exists(path):
        return {"orders": {}, "positions": {}, "meta": {}}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {"orders": {}, "positions": {}, "meta": {}}
    data.setdefault("orders", {})
    data.setdefault("positions", {})
    data.setdefault("meta", {})
    return data


def save_state(state: dict[str, Any], path: str = "state.json") -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
