import argparse
import os
import time

from dotenv import load_dotenv
from tavily import TavilyClient

from core.agent import configure_model
from core.runner import run_once
from core.strategy_loader import load as load_strategy
from integrations.alpaca.client import create_trading_client
from schemas.deps import Deps

# defaults
DEFAULT_MODEL = "anthropic:claude-sonnet-4-5-20250929"
DEFAULT_STRATEGY = "strategies/examples/sol-momentum.yaml"
DB_PATH = "state/state.db"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Options Trading Bot - multi-asset trading bot")
    parser.add_argument(
        "--strategy",
        default=os.environ.get("STRATEGY_PATH", DEFAULT_STRATEGY),
        help="Path to strategy YAML file",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("MODEL_SPEC", DEFAULT_MODEL),
        help="PydanticAI model spec (provider:model)",
    )
    parser.add_argument(
        "--allow-trading",
        action="store_true",
        default=os.environ.get("ALLOW_TRADING", "false").lower() == "true",
        help="Enable order execution (default: disabled)",
    )
    return parser.parse_args()


def main():
    load_dotenv()
    args = parse_args()

    # load strategy
    strategy = load_strategy(args.strategy)
    print(f"Loaded strategy: {strategy.name} (v{strategy.version})")

    # configure model
    configure_model(args.model, strict=True)

    # build deps
    trading_mode = os.environ.get("TRADING_MODE", "paper")
    tavily_key = os.environ.get("TAVILY_API_KEY", "")

    deps = Deps(
        alpaca=create_trading_client(trading_mode),
        tavily=TavilyClient(api_key=tavily_key) if tavily_key else None,
        allow_trading=args.allow_trading,
    )

    state_key = strategy.name
    print(f"Trading mode: {trading_mode}")
    print(f"Trading enabled: {deps.allow_trading}")
    print(f"State key: {state_key}")

    try:
        while True:
            try:
                sleep_s = run_once(
                    deps,
                    strategy=strategy,
                    poll_sleep_seconds=30,
                    db_path=DB_PATH,
                    state_key=state_key,
                )
            except Exception as e:
                print("Loop error:", repr(e))
                sleep_s = 30

            time.sleep(max(int(sleep_s), 1))
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
