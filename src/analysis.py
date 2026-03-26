"""Core analysis functions for Polymarket YES bias.

All functions are pure: take data in, return structured results out.
No side effects, no file I/O, no prints.
"""

import numpy as np
import pandas as pd
from scipy import stats


def compute_trade_matrix(df: pd.DataFrame) -> dict:
    """Compute the raw 2x2 trade matrix: {YES, NO} x {BUY, SELL}.

    Returns dict with raw counts and percentages. No interpretation --
    just the numbers. This is the foundation all other analysis builds on.
    """
    yes = df[df["token_type"] == "YES"]
    no = df[df["token_type"] == "NO"]

    yes_buy = int((yes["side"] == "BUY").sum())
    yes_sell = int((yes["side"] == "SELL").sum())
    no_buy = int((no["side"] == "BUY").sum())
    no_sell = int((no["side"] == "SELL").sum())
    total = yes_buy + yes_sell + no_buy + no_sell

    return {
        "yes_buy": yes_buy,
        "yes_sell": yes_sell,
        "no_buy": no_buy,
        "no_sell": no_sell,
        "total_trades": total,
        "total_yes": yes_buy + yes_sell,
        "total_no": no_buy + no_sell,
        "total_buy": yes_buy + no_buy,
        "total_sell": yes_sell + no_sell,
        # Proportions (of total)
        "pct_yes_buy": float(yes_buy / total * 100) if total > 0 else 0,
        "pct_yes_sell": float(yes_sell / total * 100) if total > 0 else 0,
        "pct_no_buy": float(no_buy / total * 100) if total > 0 else 0,
        "pct_no_sell": float(no_sell / total * 100) if total > 0 else 0,
        # Token split
        "pct_yes_activity": float((yes_buy + yes_sell) / total * 100) if total > 0 else 0,
        "pct_no_activity": float((no_buy + no_sell) / total * 100) if total > 0 else 0,
    }


def test_yes_vs_no_bias(df: pd.DataFrame) -> dict:
    """Test whether people buy YES more than they buy NO.

    Of all BUY trades, what proportion target YES tokens vs NO tokens?
    Uses a two-sided binomial test against H0: p(YES buy) = 0.5.

    This is the core bias test: do traders systematically prefer
    betting on outcomes happening over outcomes not happening?
    """
    buys = df[df["side"] == "BUY"]
    n = len(buys)
    if n == 0:
        return {"error": "No BUY trades in dataset"}

    yes_buys = int((buys["token_type"] == "YES").sum())
    no_buys = n - yes_buys
    p_hat = yes_buys / n

    binom_result = stats.binomtest(yes_buys, n, p=0.5, alternative="two-sided")

    # Wilson score 95% CI
    z = 1.96
    denom = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denom
    spread = z * np.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * n)) / n) / denom
    ci_low = max(0, center - spread)
    ci_high = min(1, center + spread)

    return {
        "total_buys": n,
        "yes_buys": yes_buys,
        "no_buys": no_buys,
        "yes_buy_pct": float(p_hat * 100),
        "p_value": float(binom_result.pvalue),
        "significant": binom_result.pvalue < 0.05,
        "ci_95_low": float(ci_low * 100),
        "ci_95_high": float(ci_high * 100),
    }


def compute_trade_matrix_per_category(df: pd.DataFrame) -> list[dict]:
    """Compute 2x2 trade matrix (YES/NO x BUY/SELL) per category.

    Returns list of dicts, one per category, with raw counts.
    """
    results = []
    for cat in sorted(df["category"].unique()):
        cat_df = df[df["category"] == cat]
        matrix = compute_trade_matrix(cat_df)
        matrix["category"] = cat
        results.append(matrix)
    return results


def test_yes_vs_no_per_category(df: pd.DataFrame) -> list[dict]:
    """Test YES vs NO buying bias per category.

    For each category, of all BUY trades, what proportion target YES?
    Binomial test: H0: p(YES buy) = 0.5.
    """
    results = []

    for cat in sorted(df["category"].unique()):
        cat_buys = df[(df["category"] == cat) & (df["side"] == "BUY")]
        n = len(cat_buys)
        if n == 0:
            continue

        yes_buys = int((cat_buys["token_type"] == "YES").sum())
        no_buys = n - yes_buys
        p_hat = yes_buys / n

        binom_result = stats.binomtest(yes_buys, n, p=0.5, alternative="two-sided")

        z = 1.96
        denom = 1 + z**2 / n
        center = (p_hat + z**2 / (2 * n)) / denom
        spread = z * np.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * n)) / n) / denom
        ci_low = max(0, center - spread)
        ci_high = min(1, center + spread)

        results.append({
            "category": cat,
            "total_buys": n,
            "yes_buys": yes_buys,
            "no_buys": no_buys,
            "yes_buy_pct": float(p_hat * 100),
            "p_value": float(binom_result.pvalue),
            "significant": binom_result.pvalue < 0.05,
            "ci_95_low": float(ci_low * 100),
            "ci_95_high": float(ci_high * 100),
        })

    return results


def compute_overall_bias(df: pd.DataFrame) -> dict:
    """Compute overall YES buying bias metrics.

    Returns dict with total trades, YES buy percentages (count and volume),
    and buy:sell ratios.
    """
    yes = df[df["token_type"] == "YES"]
    yes_buy = yes[yes["side"] == "BUY"]
    yes_sell = yes[yes["side"] == "SELL"]

    total_yes_vol = yes["usdc"].sum()

    return {
        "total_trades": len(df),
        "total_volume_usdc": float(df["usdc"].sum()),
        "yes_token_trades": len(yes),
        "yes_buy_count": len(yes_buy),
        "yes_sell_count": len(yes_sell),
        "yes_buy_pct_count": float(len(yes_buy) / len(yes) * 100) if len(yes) > 0 else 0,
        "yes_buy_vol": float(yes_buy["usdc"].sum()),
        "yes_sell_vol": float(yes_sell["usdc"].sum()),
        "yes_buy_pct_vol": float(yes_buy["usdc"].sum() / total_yes_vol * 100) if total_yes_vol > 0 else 0,
        "buy_sell_ratio_count": float(len(yes_buy) / len(yes_sell)) if len(yes_sell) > 0 else float("inf"),
        "buy_sell_ratio_vol": float(yes_buy["usdc"].sum() / yes_sell["usdc"].sum()) if yes_sell["usdc"].sum() > 0 else float("inf"),
    }


def compute_category_breakdown(df: pd.DataFrame) -> list[dict]:
    """Compute YES buying bias per category.

    Returns list of dicts with category, events, trades, buy counts/percentages,
    and volume, sorted by volume descending.
    """
    yes = df[df["token_type"] == "YES"]
    cat_results = []

    for cat in sorted(df["category"].unique()):
        cat_yes = yes[yes["category"] == cat]
        if len(cat_yes) == 0:
            continue

        cat_buy = cat_yes[cat_yes["side"] == "BUY"]
        cat_sell = cat_yes[cat_yes["side"] == "SELL"]
        total = len(cat_buy) + len(cat_sell)
        total_vol = float(cat_yes["usdc"].sum())

        cat_results.append({
            "category": cat,
            "events": cat_yes["event"].nunique() if "event" in cat_yes.columns else 0,
            "trades": total,
            "buy_count": len(cat_buy),
            "sell_count": len(cat_sell),
            "buy_pct_count": float(len(cat_buy) / total * 100) if total > 0 else 0,
            "buy_pct_vol": float(cat_buy["usdc"].sum() / total_vol * 100) if total_vol > 0 else 0,
            "volume_usdc": total_vol,
        })

    return sorted(cat_results, key=lambda x: x["volume_usdc"], reverse=True)


def chi_squared_test(df: pd.DataFrame) -> dict:
    """Run chi-squared test of independence on YES buy proportions across categories.

    H0: YES buy proportion is the same across all categories.
    H1: At least one category has a different proportion.

    Returns dict with test statistic, p-value, degrees of freedom,
    significance flags, and interpretation.
    """
    yes = df[df["token_type"] == "YES"]
    contingency_buy = []
    contingency_sell = []

    for cat in sorted(df["category"].unique()):
        cat_yes = yes[yes["category"] == cat]
        if len(cat_yes) == 0:
            continue
        contingency_buy.append(len(cat_yes[cat_yes["side"] == "BUY"]))
        contingency_sell.append(len(cat_yes[cat_yes["side"] == "SELL"]))

    if len(contingency_buy) < 2:
        return {"error": "Need at least 2 categories"}

    contingency_table = [contingency_buy, contingency_sell]
    chi2, p_value, dof, expected = stats.chi2_contingency(contingency_table)

    return {
        "statistic": float(chi2),
        "p_value": float(p_value),
        "degrees_of_freedom": int(dof),
        "significant_at_005": p_value < 0.05,
        "significant_at_001": p_value < 0.01,
        "interpretation": (
            "YES buying bias differs significantly across categories"
            if p_value < 0.05
            else "No significant difference in YES bias across categories"
        ),
    }


def compute_price_buckets(
    df: pd.DataFrame,
    bucket_width: float = 0.10,
    price_min: float = 0.0,
    price_max: float = 1.0,
) -> pd.DataFrame:
    """Bin YES trades by price and compute buy percentage per bucket.

    Returns DataFrame with columns: bucket, trades, buy_pct.
    """
    yes = df[df["token_type"] == "YES"].copy()

    bins = np.arange(price_min, price_max + bucket_width, bucket_width)
    labels = [f"{int(b*100)}-{int((b+bucket_width)*100)}%" for b in bins[:-1]]
    yes["price_bucket"] = pd.cut(yes["price"], bins=bins, labels=labels)

    rows = []
    for label in labels:
        bucket = yes[yes["price_bucket"] == label]
        if len(bucket) > 0:
            buy_pct = float((bucket["side"] == "BUY").mean() * 100)
            rows.append({
                "bucket": label,
                "trades": len(bucket),
                "buy_pct": buy_pct,
            })

    return pd.DataFrame(rows)


def compute_price_bias(
    df: pd.DataFrame,
    price_min: float = 0.10,
    price_max: float = 0.95,
    bucket_width: float = 0.05,
    min_trades_per_bucket: int = 10,
) -> pd.DataFrame:
    """Detailed price-vs-bias analysis with Wilson score confidence intervals.

    Filters YES trades to [price_min, price_max], bins into buckets,
    computes buy % with 95% Wilson CIs per bucket.

    Returns DataFrame with columns: bucket, midpoint, trades, buy_count,
    sell_count, buy_pct, ci_low, ci_high.
    """
    yes = df[df["token_type"] == "YES"].copy()
    yes = yes[(yes["price"] >= price_min) & (yes["price"] <= price_max)]

    bin_start = max(0, np.floor(price_min * 20) / 20)
    bin_end = min(1.05, np.ceil(price_max * 20) / 20 + bucket_width)
    bins = np.arange(bin_start, bin_end, bucket_width)
    labels = [f"{int(b*100)}-{int((b+bucket_width)*100)}%" for b in bins[:-1]]
    yes["bucket"] = pd.cut(yes["price"], bins=bins, labels=labels, include_lowest=True)

    rows = []
    z = 1.96  # 95% confidence

    for label in labels:
        bucket = yes[yes["bucket"] == label]
        n = len(bucket)
        if n < min_trades_per_bucket:
            continue

        buy_count = int((bucket["side"] == "BUY").sum())
        sell_count = n - buy_count
        buy_pct = buy_count / n * 100

        # Wilson score interval
        p_hat = buy_count / n
        denom = 1 + z**2 / n
        center = (p_hat + z**2 / (2 * n)) / denom
        spread = z * np.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * n)) / n) / denom
        ci_low = max(0, center - spread) * 100
        ci_high = min(1, center + spread) * 100

        rows.append({
            "bucket": label,
            "midpoint": bins[labels.index(label)] + bucket_width / 2,
            "trades": n,
            "buy_count": buy_count,
            "sell_count": sell_count,
            "buy_pct": buy_pct,
            "ci_low": ci_low,
            "ci_high": ci_high,
        })

    return pd.DataFrame(rows)


def price_bias_correlation(results_df: pd.DataFrame) -> dict:
    """Compute Pearson correlation between price midpoint and buy percentage.

    Returns dict with correlation coefficient, p-value, and interpretation.
    """
    if len(results_df) < 3:
        return {"error": "Need at least 3 buckets for correlation"}

    corr, p_value = stats.pearsonr(results_df["midpoint"], results_df["buy_pct"])

    if p_value < 0.05:
        direction = "increases" if corr > 0 else "decreases"
        interpretation = f"Statistically significant: buy% {direction} with price"
    else:
        interpretation = "No significant linear relationship between price and buy%"

    return {
        "correlation": float(corr),
        "p_value": float(p_value),
        "significant_at_005": p_value < 0.05,
        "interpretation": interpretation,
    }


# ---------------------------------------------------------------------------
# Calibration and P&L (resolution-based analysis)
# ---------------------------------------------------------------------------

def compute_market_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """Compute volume-weighted average price (VWAP) per market for YES token buys.

    Returns one row per market with: question, vwap, total_usdc, n_trades, resolved_yes.
    Only includes markets with YES BUY trades and a known resolution.
    """
    yes_buys = df[(df["token_type"] == "YES") & (df["side"] == "BUY")].copy()
    yes_buys = yes_buys[yes_buys["resolved_yes"].notna()]

    if len(yes_buys) == 0:
        return pd.DataFrame()

    # VWAP = sum(price * usdc) / sum(usdc) -- volume-weighted by dollar amount
    grouped = yes_buys.groupby("question").agg(
        total_price_x_vol=("price", lambda x: (x * yes_buys.loc[x.index, "usdc"]).sum()),
        total_usdc=("usdc", "sum"),
        n_trades=("timestamp", "count"),
        resolved_yes=("resolved_yes", "first"),
    ).reset_index()

    grouped["vwap"] = grouped["total_price_x_vol"] / grouped["total_usdc"]
    grouped = grouped.drop(columns=["total_price_x_vol"])

    return grouped


def compute_calibration(df: pd.DataFrame, n_buckets: int = 5) -> pd.DataFrame:
    """Calibration analysis: do YES prices predict resolution outcomes?

    Groups markets by VWAP bucket, then computes actual YES resolution rate
    per bucket. If markets are well-calibrated, VWAP ≈ resolution rate.

    Returns DataFrame with: bucket, midpoint, n_markets, avg_vwap,
    resolution_rate, overpricing (vwap - resolution_rate).
    """
    market_vwap = compute_market_vwap(df)
    if len(market_vwap) == 0:
        return pd.DataFrame()

    # Create equal-width buckets
    bins = np.linspace(0, 1, n_buckets + 1)
    labels = [f"{int(bins[i]*100)}-{int(bins[i+1]*100)}%" for i in range(n_buckets)]
    market_vwap["bucket"] = pd.cut(market_vwap["vwap"], bins=bins, labels=labels, include_lowest=True)

    rows = []
    for label in labels:
        bucket = market_vwap[market_vwap["bucket"] == label]
        n = len(bucket)
        if n == 0:
            continue
        avg_vwap = float(bucket["vwap"].mean())
        resolution_rate = float(bucket["resolved_yes"].mean())
        rows.append({
            "bucket": label,
            "midpoint": (bins[labels.index(label)] + bins[labels.index(label) + 1]) / 2,
            "n_markets": n,
            "avg_vwap": avg_vwap,
            "resolution_rate": resolution_rate,
            "overpricing": avg_vwap - resolution_rate,
        })

    return pd.DataFrame(rows)


def compute_buyer_pnl(df: pd.DataFrame) -> dict:
    """Compute average P&L for YES buyers vs NO buyers.

    For each BUY trade:
      - YES buyer P&L = (1 if resolved YES, else 0) - price_paid
      - NO buyer P&L = (1 if resolved NO, else 0) - price_paid

    Returns dict with mean P&L per trade, total P&L, and trade counts
    for each token type.
    """
    buys = df[df["side"] == "BUY"].copy()
    buys = buys[buys["resolved_yes"].notna()]

    yes_buys = buys[buys["token_type"] == "YES"].copy()
    no_buys = buys[buys["token_type"] == "NO"].copy()

    # YES buyer: pays price, receives 1 if resolved YES, else 0
    yes_buys["pnl"] = yes_buys["resolved_yes"].astype(float) - yes_buys["price"]
    # NO buyer: pays price, receives 1 if resolved NO, else 0
    no_buys["pnl"] = (~no_buys["resolved_yes"]).astype(float) - no_buys["price"]

    return {
        "yes_buyer_mean_pnl": float(yes_buys["pnl"].mean()) if len(yes_buys) > 0 else 0,
        "yes_buyer_total_pnl": float(yes_buys["pnl"].sum()) if len(yes_buys) > 0 else 0,
        "yes_buyer_n_trades": len(yes_buys),
        "no_buyer_mean_pnl": float(no_buys["pnl"].mean()) if len(no_buys) > 0 else 0,
        "no_buyer_total_pnl": float(no_buys["pnl"].sum()) if len(no_buys) > 0 else 0,
        "no_buyer_n_trades": len(no_buys),
        "pnl_gap": float(yes_buys["pnl"].mean() - no_buys["pnl"].mean()) if len(yes_buys) > 0 and len(no_buys) > 0 else 0,
    }
