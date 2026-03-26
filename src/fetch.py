"""Data fetching for Polymarket YES bias analysis.

Handles market discovery via Gamma API and trade fetching via Goldsky subgraph.
All functions implement check-before-fetch caching to the data/ directory.

Each trade is tagged with metadata for downstream slicing:
  - category: Polymarket category (Politics, Crypto, Sports, Finance, Culture)
  - event_title: Parent event name
  - question: Specific market question
  - token_type: YES or NO
  - side: BUY or SELL
  - num_markets_in_event: How many markets the parent event contains
  - neg_risk: Whether the event uses negRisk (mutually exclusive outcomes)
"""

import json
import time
from pathlib import Path

import pandas as pd
import requests

from .config import GAMMA_API, SUBGRAPH_URL, CATEGORIES, DATA_DIR


# ---------------------------------------------------------------------------
# Trade transformation (shared across all analyses)
# ---------------------------------------------------------------------------

def transform_fill(fill: dict, token_id: str, token_label: str) -> dict | None:
    """Transform a raw OrderFilled event into normalized trade data.

    Args:
        fill: Raw OrderFilled event from Goldsky.
        token_id: The token ID we queried for (used to verify match).
        token_label: "YES" or "NO" -- which token this trade is for.

    Side determination logic:
      makerAssetId == "0" (USDC) -> maker BOUGHT tokens -> side = BUY
      takerAssetId == "0" (USDC) -> maker SOLD tokens -> side = SELL

    Price = USDC / tokens (both raw values divided by 1e6 for blockchain decimals).
    Trades with price outside (0, 1.5) are filtered as outliers.
    """
    maker_asset = str(fill.get("makerAssetId", ""))
    taker_asset = str(fill.get("takerAssetId", ""))
    maker_amt = int(fill.get("makerAmountFilled", 0))
    taker_amt = int(fill.get("takerAmountFilled", 0))

    if maker_amt == 0 or taker_amt == 0:
        return None

    if maker_asset == "0":
        usdc, tokens, token_asset, side = maker_amt, taker_amt, taker_asset, "BUY"
    elif taker_asset == "0":
        usdc, tokens, token_asset, side = taker_amt, maker_amt, maker_asset, "SELL"
    else:
        return None

    price = (usdc / 1e6) / (tokens / 1e6)
    if not (0 < price < 1.5):
        return None

    return {
        "timestamp": int(fill.get("timestamp", 0)),
        "transaction_hash": fill.get("transactionHash", ""),
        "price": price,
        "side": side,
        "token_type": token_label,
        "volume": tokens / 1e6,
        "usdc": usdc / 1e6,
        "maker": fill.get("maker", ""),
        "taker": fill.get("taker", ""),
    }


# ---------------------------------------------------------------------------
# Goldsky subgraph fetching
# ---------------------------------------------------------------------------

def fetch_trades_for_token(
    token_id: str, token_label: str = "YES",
    batch_size: int = 1000, max_trades: int = 5000
) -> list[dict]:
    """Fetch trades for a single token from Goldsky subgraph.

    Args:
        token_id: The ERC-1155 token ID to query.
        token_label: "YES" or "NO" -- labels each trade with which token it's for.

    Queries both sides separately (makerAssetId and takerAssetId)
    then merges and deduplicates by event ID. This ensures both BUY
    and SELL trades are captured.
    """
    all_trades = {}

    for side_field in ("makerAssetId", "takerAssetId"):
        side_count = 0
        skip = 0
        while side_count < max_trades:
            query = f"""
            {{
                orderFilledEvents(
                    where: {{ {side_field}: "{token_id}" }}
                    orderBy: timestamp
                    orderDirection: asc
                    first: {batch_size}
                    skip: {skip}
                ) {{
                    id
                    timestamp
                    maker
                    taker
                    makerAssetId
                    takerAssetId
                    makerAmountFilled
                    takerAmountFilled
                    transactionHash
                }}
            }}
            """
            try:
                resp = requests.post(
                    SUBGRAPH_URL, json={"query": query}, timeout=30
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f"    Goldsky error: {e}")
                break

            if "errors" in data:
                print(f"    GraphQL error: {data['errors']}")
                break

            fills = data.get("data", {}).get("orderFilledEvents", [])
            if not fills:
                break

            for f in fills:
                parsed = transform_fill(f, token_id=token_id, token_label=token_label)
                if parsed:
                    parsed["token_id"] = token_id
                    key = f.get("id", f"{parsed['transaction_hash']}_{parsed['timestamp']}")
                    all_trades[key] = parsed
                    side_count += 1

            skip += batch_size
            if len(fills) < batch_size:
                break

            time.sleep(0.2)

    trades = list(all_trades.values())
    trades.sort(key=lambda t: t["timestamp"])
    return trades[:max_trades]


# ---------------------------------------------------------------------------
# Market discovery and fetching
# ---------------------------------------------------------------------------

def discover_and_fetch_category(
    category: str,
    max_events: int = 50,
    max_markets: int = 100,
    max_trades_per_token: int = 1000,
) -> pd.DataFrame:
    """Discover resolved markets and fetch trades for a single category.

    No filtering by event type -- every event is tagged with metadata
    so analysis notebooks can slice as needed:
      - num_markets_in_event: 1 = pure binary, 2+ = multi-outcome
      - neg_risk: True = mutually exclusive outcomes (negRisk event)

    The max_markets cap limits total API calls per category (each market
    requires 2 token queries). Events are processed in volume order;
    once max_markets is reached, remaining events are skipped.

    Args:
        category: Key from CATEGORIES dict.
        max_events: Number of resolved events to discover (sorted by volume desc).
        max_markets: Maximum total markets (token pairs) to process per category.
        max_trades_per_token: Cap on trades fetched per token (YES or NO).
    """
    tag_id = CATEGORIES[category]
    # Gamma API may return fewer than requested; fetch generously
    fetch_limit = max(max_events * 2, 200)

    print(f"Discovering {category} markets (tag_id={tag_id})...")

    resp = requests.get(
        f"{GAMMA_API}/events",
        params={
            "tag_id": tag_id,
            "closed": "true",
            "limit": fetch_limit,
            "order": "volume",
            "ascending": "false",
        },
        timeout=30,
    )
    events = resp.json()

    # Take up to max_events, but skip events with zero markets
    events = [e for e in events if len(e.get("markets", [])) >= 1][:max_events]
    print(f"  {len(events)} events discovered")

    # Build token pairs with full metadata, respecting market cap
    token_pairs = []
    events_used = 0
    for event in events:
        if len(token_pairs) >= max_markets:
            break

        title = event.get("title", "")
        num_markets = len(event.get("markets", []))
        neg_risk = bool(event.get("negRisk", False))

        for market in event.get("markets", []):
            if len(token_pairs) >= max_markets:
                break
            clob_ids = market.get("clobTokenIds", [])
            if isinstance(clob_ids, str):
                try:
                    clob_ids = json.loads(clob_ids)
                except (json.JSONDecodeError, TypeError):
                    continue
            if not clob_ids:
                continue

            token_pairs.append({
                "yes_token": clob_ids[0],
                "no_token": clob_ids[1] if len(clob_ids) > 1 else None,
                "question": market.get("question", title),
                "event": title,
                "num_markets_in_event": num_markets,
                "neg_risk": neg_risk,
            })
        events_used += 1

    print(f"  {len(token_pairs)} markets from {events_used} events (cap: {max_markets})\n")

    all_trades = []
    for i, pair in enumerate(token_pairs):
        print(f"  [{i+1}/{len(token_pairs)}] {pair['question'][:65]}...")

        # Fetch YES token trades
        yes_trades = fetch_trades_for_token(
            pair["yes_token"], token_label="YES", max_trades=max_trades_per_token
        )
        for t in yes_trades:
            t["question"] = pair["question"]
            t["event"] = pair["event"]
            t["num_markets_in_event"] = pair["num_markets_in_event"]
            t["neg_risk"] = pair["neg_risk"]
        all_trades.extend(yes_trades)
        print(f"    YES -> {len(yes_trades):,} trades")

        # Fetch NO token trades
        no_token = pair.get("no_token")
        if no_token:
            no_trades = fetch_trades_for_token(
                no_token, token_label="NO", max_trades=max_trades_per_token
            )
            for t in no_trades:
                t["question"] = pair["question"]
                t["event"] = pair["event"]
                t["num_markets_in_event"] = pair["num_markets_in_event"]
                t["neg_risk"] = pair["neg_risk"]
            all_trades.extend(no_trades)
            print(f"    NO  -> {len(no_trades):,} trades")

    df = pd.DataFrame(all_trades)
    print(f"\nTotal: {len(df):,} trades fetched for {category}")
    return df


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def load_or_fetch_all_categories(
    max_events_per_category: int = 50,
    max_markets_per_category: int = 100,
    max_trades_per_token: int = 1000,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Fetch trades across all categories, tagged with metadata.

    Single cache file: data/trades_all.parquet
    Discovery metadata: data/discovery_summary.json

    Each trade includes: category, event_title, question, token_type, side,
    num_markets_in_event, neg_risk -- enabling any downstream slicing.
    """
    cache_path = DATA_DIR / "trades_all.parquet"
    summary_path = DATA_DIR / "discovery_summary.json"

    if cache_path.exists() and not force_refresh:
        print(f"Loading cached trades from {cache_path.name}")
        df = pd.read_parquet(str(cache_path))
        print(f"Loaded {len(df):,} trades")
        return df

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    all_dfs = []
    summary = {}

    for category in CATEGORIES:
        print(f"\n{'='*60}")
        try:
            df_cat = discover_and_fetch_category(
                category,
                max_events=max_events_per_category,
                max_markets=max_markets_per_category,
                max_trades_per_token=max_trades_per_token,
            )
        except Exception as e:
            print(f"  ERROR fetching {category}: {e}")
            print(f"  Skipping category, continuing with remaining...")
            continue
        if len(df_cat) > 0:
            df_cat["category"] = category
            all_dfs.append(df_cat)
            summary[category] = {
                "trades": len(df_cat),
                "events": int(df_cat["event"].nunique()),
                "markets": int(df_cat["question"].nunique()),
                "yes_trades": int((df_cat["token_type"] == "YES").sum()),
                "no_trades": int((df_cat["token_type"] == "NO").sum()),
            }

    df = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()

    if len(df) > 0:
        df.to_parquet(str(cache_path), index=False)
        print(f"\nCached {len(df):,} trades to {cache_path.name}")

    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    return df


# ---------------------------------------------------------------------------
# Population-level resolution data (no trade fetching -- metadata only)
# ---------------------------------------------------------------------------

def fetch_resolution_population(
    max_offset: int = 10000,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Fetch resolution outcomes for ALL resolved single-market events on Polymarket.

    This does NOT fetch trade data -- only event/market metadata from the Gamma API.
    Much faster than trade fetching: ~5 min for 10K events vs hours for trades.

    For each single-market event, records:
      - event title, question, category
      - resolved_yes (True/False) derived from outcomePrices final settlement
      - outcomePrices (raw settlement prices)

    Cache: data/resolution_population.parquet

    Returns DataFrame with one row per resolved single-market event.
    """
    cache_path = DATA_DIR / "resolution_population.parquet"

    if cache_path.exists() and not force_refresh:
        print(f"Loading cached resolution data from {cache_path.name}")
        df = pd.read_parquet(str(cache_path))
        print(f"Loaded {len(df):,} single-market events")
        return df

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    offset = 0

    while offset < max_offset:
        resp = requests.get(
            f"{GAMMA_API}/events",
            params={"closed": "true", "limit": 100, "offset": offset},
            timeout=30,
        )
        resp.raise_for_status()
        events = resp.json()
        if not events:
            break

        for e in events:
            markets = e.get("markets", [])
            if len(markets) != 1:
                continue

            m = markets[0]

            # Parse settlement prices
            prices_raw = m.get("outcomePrices", "[]")
            if isinstance(prices_raw, str):
                try:
                    prices = json.loads(prices_raw)
                except (json.JSONDecodeError, TypeError):
                    continue
            else:
                prices = prices_raw

            if not prices:
                continue

            yes_price = float(prices[0])
            if yes_price == 0.5:
                continue  # ambiguous settlement

            # Extract category from tags
            tags = e.get("tags", [])
            category = "Unknown"
            for t in (tags if isinstance(tags, list) else []):
                label = t.get("label", "") if isinstance(t, dict) else ""
                if label in (
                    "Politics", "Crypto", "Sports", "Finance", "Culture",
                    "Science", "Tech", "Entertainment", "World", "Business",
                ):
                    category = label
                    break

            rows.append({
                "event_title": e.get("title", ""),
                "question": m.get("question", e.get("title", "")),
                "category": category,
                "resolved_yes": yes_price > 0.5,
                "yes_settlement_price": yes_price,
                "closed_time": m.get("closedTime", ""),
                "volume": float(e.get("volume", 0)),
            })

        offset += 100
        if len(events) < 100:
            break
        if offset % 2000 == 0:
            print(f"  ...scanned {offset} events, {len(rows)} single-market so far")
        time.sleep(0.2)

    df = pd.DataFrame(rows)
    if len(df) > 0:
        df.to_parquet(str(cache_path), index=False)
        print(f"Cached {len(df):,} single-market events to {cache_path.name}")

    return df
