"""Shared configuration for Polymarket YES bias analysis."""

from pathlib import Path

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

GAMMA_API = "https://gamma-api.polymarket.com"

# Goldsky subgraph endpoint (public, no auth required)
SUBGRAPH_URL = (
    "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw"
    "/subgraphs/orderbook-subgraph/0.0.1/gn"
)

# ---------------------------------------------------------------------------
# Polymarket category tag IDs (discovered from /tags and /events endpoints)
# ---------------------------------------------------------------------------

CATEGORIES = {
    "Politics": 2,
    "Crypto": 21,
    "Sports": 1,
    "Finance": 120,
    "Culture": 596,
}

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
