from __future__ import annotations

import json
import os
import time
from typing import Any

DEFAULT_STATE = {
    "orders": {},
    "positions": {},
    "last_run_ts": 0,
}


def load_state(path: str = "state.json") -> dict[str, Any]:
    if not os.path.exists(path):
        return dict(DEFAULT_STATE)
    with open(path, "r") as f:
        return json.load(f)


def save_state(state: dict[str, Any], path: str = "state.json") -> None:
    state["last_run_ts"] = int(time.time())
    with open(path, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
