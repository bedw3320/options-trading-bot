import os

from dotenv import load_dotenv
from tavily import TavilyClient

from core.runner import run_once
from integrations.alpaca.config import load_config
from schemas.deps import Deps


def main():
    load_dotenv()

    deps = Deps(
        alpaca=load_config(),
        tavily=TavilyClient(api_key=os.environ["TAVILY_API_KEY"]),
        allow_trading=os.getenv("ALLOW_TRADING", "false").lower() == "true",
    )

    run_once(
        deps,
        prompt="Scan recent news for SOL and give buy/sell/hold with sources.",
        conf_threshold=0.75,
        poll_sleep_seconds=30,
    )


if __name__ == "__main__":
    main()
