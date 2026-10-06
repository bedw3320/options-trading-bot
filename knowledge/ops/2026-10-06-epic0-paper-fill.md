# Epic 0 evidence — first paper fill (2026-10-06, ET)

- Gateway: gnzsnz container was stuck in an IBC "Re-login is required" loop since 2026-09-27; `docker compose restart ib-gateway` 09:30 ET → logged in "DUT116016 (Simulated Trading)". (Healthcheck shows unhealthy only because `nc` is missing in the image.)
- Identity: `core.paper_readiness` → `OK account=DUT116016 mode=paper`; managedAccounts == ('DUT116016',). Host for local runs must be 127.0.0.1 (.env IB_GATEWAY_HOST=ib-gateway is the compose-internal name).
- Orders (via `GuardedBroker` preview→token→confirm with place_fn; SPY STK SMART, 1 sh, MKT, DAY, RTH):
  - BUY  orderId 4 permId 1741358825 execId 00025b49.6ac58ef0.01.01 @ 778.25 ARCA 09:35:19 ET, comm $1.00
  - SELL orderId 8 permId 1741358826 execId 00025b49.6ac59033.01.01 @ 778.18 ARCA 09:35:35 ET, comm $1.02
- Paper book: a pre-existing 1 SPY (avg 760.07, from an earlier session) was already held; it remains (not touched).
- SQLite: `state/state.db` table `agent_events`, state_key `epic0-manual`, ids 1–9 (order_placed, order_result, fill, fill_time_correction, quotes_probe). Fill `time_et` in ids 3/6 is UTC mislabeled; id 7 holds corrected ET.
- Quotes (marketDataType=1 and 3): SPY and SPY 20261023 778 C/P → bid/ask/last/Greeks all NaN. Error 10197 "No market data during competing live session"; historical 162 "Trading TWS session is connected from a different IP address". Option chain defs OK (33 expirations, 491 strikes, tradingClass SPY).
- Blocker: the live user (U28048141) has an active session elsewhere (TWS/mobile/portal) which takes the shared market data. Next step: log the live session out during RTH, then rerun the quotes probe.
