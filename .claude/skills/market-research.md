## Market Research Skill

You can research tickers, sectors, and market conditions using the data sources available in the Options Trading Bot platform.

### Available Data Sources

1. **Price Data** (`integrations/alpaca/market_data.py`)
   - `get_stock_bars(symbol, timeframe, bars)` - Stock OHLCV
   - `get_crypto_bars(symbol, timeframe, bars)` - Crypto OHLCV
   - `get_stock_quote(symbol)` - Latest bid/ask

2. **Technical Indicators** (`integrations/data/technicals.py`)
   - `compute_indicator(df, {"name": "RSI", "period": 14})`
   - `compute_all(df, indicators_list)`
   - Supported: RSI, SMA, EMA, VWAP, MACD, BBANDS, ATR, VOLUME_RATIO

3. **News** (`integrations/data/news.py`)
   - `aggregate_news(tavily_client, symbols, keywords=[], max_results=10)`
   - Sources: Tavily web search + Alpaca News API

4. **Social Sentiment** (`integrations/data/social.py`)
   - `search_reddit(keywords, subreddits=[], limit=25)`
   - `search_stocktwits(symbol, limit=20)`
   - `aggregate_social(symbols, subreddits=[])`

5. **Options Flow** (`integrations/data/options_flow.py`)
   - `analyze_options_flow(client, symbol, min_dte=0, max_dte=45)`
   - Returns put/call ratio, open interest analysis

### Research Approach
When researching a ticker or market condition:
1. Start with price data and key technicals
2. Check recent news for catalysts
3. Look at social sentiment for retail interest
4. If options are relevant, check unusual activity
5. Synthesize findings into a clear summary with confidence level
