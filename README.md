# Polymarket YES Bias: An Empirical Analysis

Do prediction market traders prefer YES tokens? We tested three hypotheses using 28,793 on-chain trades across 88 resolved Polymarket markets, plus resolution data from 7,292 single-market events.

**TL;DR:** What's commonly called "YES bias" may be longshot bias channelled through question framing. Traders buy whichever token is cheap — and Polymarket's editorial structure makes YES the cheap token in most markets.

## Key Findings

1. **Single-market events resolve NO 59% of the time** (n=7,292). The "Will X happen?" framing produces NO-heavy base rates. Sports (symmetric framing) → 47% YES. Politics → 31%. Culture → 21%.

2. **Trade counts can't detect YES bias.** 51.2% of buys target YES (p=0.0001) but the effect is 1.3pp — constrained by order book mechanics (YES + NO = $1).

3. **The trade-size gradient is a price composition effect.** Small trades (<$20) are 56% YES, large trades ($500+) are 37% YES. But within each price bucket, all sizes behave the same. Small money clusters where tokens are cheap.

4. **Traders buy whatever's cheap, not whatever's labeled YES.** At low prices, ~90% of buys are YES. At high prices, ~90% are NO. At mid-prices, it's 50/50. The preference follows price, not the label.

## Quickstart

```bash
cd sprints/yes-bias/analysis
pip install -r requirements.txt
jupyter notebook
```

Run notebooks in order: **01 → 02 → 03**

- **01** fetches and caches data from Polymarket APIs (~5-10 min first run, instant on subsequent runs)
- **02** runs the core bias analysis (hypotheses H1-H3, charts 01-15)
- **03** analyses resolution rates at population level (charts 16-18)

All data is cached in `data/` after first run. Subsequent notebook runs use cached data and execute in seconds.

## Data Sources

- **[Gamma API](https://gamma-api.polymarket.com)** — market discovery (resolved events, metadata)
- **[Goldsky subgraph](https://api.goldsky.com)** — on-chain `OrderFilled` events from Polymarket's CTF Exchange on Polygon

All data is on-chain and independently verifiable via [Polygonscan](https://polygonscan.com). No API keys required.

## Files

```
analysis/
├── notebooks/
│   ├── 01-data-collection.ipynb              # Fetch + cache trade data
│   ├── 02-yes-bias-analysis.ipynb            # Core analysis (H1-H3 + framing)
│   └── 03-single-market-resolution-analysis  # Population resolution rates
├── src/
│   ├── config.py                             # API endpoints, paths
│   ├── fetch.py                              # Data fetching with caching
│   └── analysis.py                           # Statistical analysis functions
├── data/                                     # Cached parquet files (.gitignored)
│   ├── trades_single_market.parquet          # 28,793 trades, 88 markets
│   ├── trades_all.parquet                    # 714K trades, multi-market reference
│   └── resolution_population.parquet         # 7,292 resolved single-market events
├── output/                                   # Charts (committed)
│   ├── 01-data-overview.png ... 18-*.png     # 18 analysis charts
└── requirements.txt
```

## Methodology

1. **Market discovery:** Query Gamma API for top 500 resolved events by volume, filter to single-market events (1 question per event) → 88 markets
2. **Trade fetching:** Query Goldsky subgraph for `OrderFilled` events on both YES and NO tokens (up to 200 per token per market)
3. **Side classification:** Maker-centric. `makerAssetId == "0"` (USDC) = maker BUY, `takerAssetId == "0"` = maker SELL
4. **Resolution population:** Separate Gamma API query for all resolved single-market events (no volume filter) → 7,292 events
5. **Statistical tests:** Binomial tests, paired t-tests, point-biserial correlations, price-bucket controls

## Limitations

- 88 trade-level markets (top by volume — selection bias toward YES-resolving events)
- First 200 trades per token (skews toward early-life trading)
- Maker-centric classification (taker-side checked as robustness test — same results)
- No Mention Markets in sample (identified by other research as most bias-prone)
- Category tags inferred from question text (not from API metadata)

## Related Work

- Becker (2026), "The Microstructure of Wealth Transfer in Prediction Markets" — 72.1M trades on Kalshi
- Deleep et al. (2026), "How Wise is the Crowd?" — 5,456 markets across Polymarket and Kalshi

## License

MIT
