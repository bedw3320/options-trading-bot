# Paper readiness and gated placement

Harness only. No strategy YAML.

## Paper readiness (no orders)

On the Mini, with Gateway up and `.env` set (`TRADING_MODE=paper`, `IB_ACCOUNT_ID=DU…`):

```bash
uv run python -m core.paper_readiness
# or: uv run python scripts/paper_readiness.py
```

Prints one line and exits 0 or 1:

- `OK paper_readiness account=<id> mode=paper`
- `FAIL paper_readiness Gateway down: …`
- `FAIL paper_readiness live-looking account U…` (or mismatch / live mode / missing `IB_ACCOUNT_ID`)

Checks: connect (or report Gateway down), `TRADING_MODE=paper`, `managedAccounts` contains `IB_ACCOUNT_ID`, account looks paper (`DU*` or the configured id), abort on live-looking `U*` or port `4001`. Does not place.

## Gated path

```text
agent → OrderIntent (alias TradeIntent)
     → code risk
     → GuardedBroker.preview → single-use token
     → identity + risk re-validate
     → place
```

- Strategies must not import `ib_insync`. `OrderIntent` is the only strategy→harness object (`schemas/output.py`).
- Agent `create_order` / `close_position` tools refuse to send. Runner-only placement: `core/guarded_broker.py`.
- Identity: `core/identity.py::assert_paper_identity` before every cycle and again at preview/confirm.
- Live is not armed. Do not set `TRADING_MODE=live`.
