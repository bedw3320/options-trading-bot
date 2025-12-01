import os
import time

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
        # change if you want it to execute trades
        allow_trading=False,
    )

    base_prompt = "Scan recent news for SOL and give buy/sell/hold with sources."

    try:
        while True:
            try:
                sleep_s = run_once(
                    deps,
                    base_prompt=base_prompt,
                    conf_threshold=0.75,
                    poll_sleep_seconds=30,
                    state_path="state.json",
                )
            except Exception as e:
                print("Loop error:", repr(e))
                sleep_s = 30
            time.sleep(sleep_s)
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
