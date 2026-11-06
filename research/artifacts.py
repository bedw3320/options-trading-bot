"""Write screen artifacts under research/screens/<date>.{json,md}."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from research.models import TickerScreen


def _md_cell(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def render_markdown(screens: list[TickerScreen], *, as_of: datetime, trade_date: date) -> str:
    lines = [
        f"# Liquidity screen {trade_date.isoformat()}",
        "",
        f"as_of={as_of.isoformat()}  ",
        "All thresholds are **proposals for Will** (inherited from the SPY strategy YAML unless overridden).",
        "",
    ]
    for s in screens:
        lines.append(f"## {s.ticker} — `{s.result}`")
        lines.append("")
        lines.append(
            f"expiry={s.expiry or '-'} dte={s.dte} spot={_md_cell(s.underlying_price)} "
            f"data_source=`{s.data_source}` diagnostic_only={s.diagnostic_only}"
        )
        if s.reasons:
            lines.append("")
            lines.append("Reasons:")
            for r in s.reasons:
                lines.append(f"- {r}")
        lines += [
            "",
            "| role | occ | strike | delta | OI | volume | bid | ask | spread | spread% | age_s | source | pass |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for leg in s.legs:
            lines.append(
                "| "
                + " | ".join(
                    _md_cell(x)
                    for x in (
                        leg.role,
                        leg.occ,
                        leg.strike,
                        leg.delta,
                        leg.open_interest,
                        leg.volume,
                        leg.bid,
                        leg.ask,
                        leg.spread_abs,
                        leg.spread_pct,
                        leg.quote_age_seconds,
                        leg.data_source,
                        "yes" if leg.passed else "no",
                    )
                )
                + " |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_artifacts(
    screens: list[TickerScreen],
    *,
    output_dir: str | Path,
    trade_date: date,
    as_of: datetime,
) -> tuple[Path, Path]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "trade_date": trade_date.isoformat(),
        "as_of": as_of.isoformat(),
        "note": "PROPOSAL for Will: thresholds inherited from spy-defined-risk-rr.yaml unless overridden",
        "tickers": [s.as_dict() for s in screens],
    }
    json_path = out / f"{trade_date.isoformat()}.json"
    md_path = out / f"{trade_date.isoformat()}.md"
    json_path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    md_path.write_text(render_markdown(screens, as_of=as_of, trade_date=trade_date))
    return json_path, md_path
