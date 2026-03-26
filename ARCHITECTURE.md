# Polymarket Exchange Architecture: How YES and NO Orders Work

Research note for the YES bias sprint. Understanding this is critical for correctly interpreting on-chain trade data.

## One Shared Order Book, Two Separate Tokens

Polymarket uses a **single shared order book** per market, but YES and NO are **separate ERC-1155 tokens** on Polygon. The exchange mirrors orders across outcomes: "Buy YES at $0.60" automatically appears as "Sell NO at $0.40" on the other side.

When you click "Buy No" in the Polymarket UI, the system treats it as the complement of a YES order. Buying NO at $0.40 = Selling YES at $0.60 from the order book's perspective.

## Three On-Chain Match Types

When orders execute, the CTF Exchange contract produces `OrderFilled` events. Three distinct patterns appear:

| Match Type | What Happens | On-Chain Signature |
|------------|-------------|-------------------|
| **Direct** | Buyer purchases tokens from an existing holder | One side sends USDC (`makerAssetId=0`), other side sends tokens |
| **Minting** | YES buyer + NO buyer matched, new token pair created from $1 USDC collateral | TWO events, both with `makerAssetId=0` (both sending USDC), each receiving different token IDs |
| **Merging** | YES seller + NO seller matched, tokens burned back into USDC | TWO events, both sending tokens, both receiving USDC |

## Implications for Data Analysis

**Critical:** Querying only the YES token ID from Goldsky misses all NO token activity. Each token has its own set of `OrderFilled` events. To get the full picture:

- Query trades for the YES token ID (gets YES buys + YES sells)
- Query trades for the NO token ID (gets NO buys + NO sells)
- Combine and analyze

Without both, you can only measure order flow on the YES book (BUY YES vs SELL YES), which measures hold-to-expiry behavior, not directional preference. The meaningful bias question -- do people prefer buying YES over buying NO -- requires both order books.

## Side Determination

In each `OrderFilled` event:
- `makerAssetId == "0"` (USDC) --> maker BOUGHT tokens --> `side = BUY`
- `takerAssetId == "0"` (USDC) --> maker SOLD tokens --> `side = SELL`
- The non-zero asset ID identifies which token (YES or NO) was traded

## Sources

- [Polymarket CLOB Documentation](https://docs.polymarket.com/developers/CLOB/introduction)
- [Decoding Polymarket On-Chain Data - Zichao Yang](https://yzc.me/x01Crypto/decoding-polymarket)
- [PANews: Why YES + NO Must Equal 1](https://www.panewslab.com/en/articles/957b25f5-6f6a-4a43-8b8b-2de49661d026)
- [Nautilus Trader Issue #3126](https://github.com/nautechsystems/nautilus_trader/issues/3126) -- documents the side inversion behavior when YES/NO orders match
- [Polymarket CTF Exchange Contract](https://github.com/Polymarket/ctf-exchange)
