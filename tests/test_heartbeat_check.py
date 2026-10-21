"""Mini heartbeat checker (used by .github/workflows/mini-heartbeat.yml)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.check_heartbeat import MAX_AGE, check, main as check_main

NOW = datetime(2026, 10, 21, 19, 50, tzinfo=timezone.utc)


def _status(**over):
    base = {
        "host": "mini",
        "gateway_logged_in": True,
        "account": "DUT116016",
        "expected_account": "DUT116016",
        "last_check": "2026-10-21T19:50:11Z",
        "last_error": " ",
    }
    base.update(over)
    return base


def test_fresh_logged_in_ok():
    assert check(_status(), now=NOW) == []


def test_stale_last_check_fails():
    errs = check(_status(last_check="2026-10-21T18:00:00Z"), now=NOW)
    assert any("min old" in e for e in errs)
    assert MAX_AGE.total_seconds() == 45 * 60


def test_gateway_logged_out_fails():
    errs = check(_status(gateway_logged_in=False), now=NOW)
    assert any("gateway_logged_in" in e for e in errs)


def test_missing_last_check_fails():
    s = _status()
    del s["last_check"]
    assert any("last_check missing" in e for e in check(s, now=NOW))


def test_cli_ok_and_fail(tmp_path, capsys, monkeypatch):
    p = tmp_path / "status.json"
    p.write_text(json.dumps(_status(last_check=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))))
    assert check_main([str(p)]) == 0
    assert "OK" in capsys.readouterr().out
    p.write_text(json.dumps(_status(gateway_logged_in=False,
                                    last_check=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))))
    assert check_main([str(p)]) == 1
    assert "FAIL" in capsys.readouterr().out
    missing = tmp_path / "nope.json"
    assert check_main([str(missing)]) == 1


def test_workflow_file_has_no_secrets():
    text = (Path(__file__).resolve().parents[1] / ".github/workflows/mini-heartbeat.yml").read_text()
    assert "cron: \"*/30 13-21 * * 1-5\"" in text
    assert "secrets." not in text
    assert "check_heartbeat.py" in text
