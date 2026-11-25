"""Fixed paper-plan constants for memescan audit v1. No network. No orders."""

LABEL = (
    "NEW EXPERIMENT — memescan audit v1, started November 25, 2026, "
    "paper only, not original evidence."
)
BANNER = "Paper only. Not financial advice. No trading, no wallet."
WHY = (
    "Tests whether a rug/safety checklist actually separates memecoins that "
    "survive 24h from ones that collapse. Paper only, includes 1.5% slippage "
    "+ fees per side. Most memecoins go to zero; expect negative results — "
    "the point is to measure the checklist, not to find trades."
)

SLIPPAGE = 0.015
FEE = 0.0025
STOP_PCT = 0.25
TP1_PCT = 1.0
TP1_FRACTION = 0.5
TRAIL = 0.35
DEAD_AFTER_S = 45 * 60
DEAD_BELOW_GAIN = 0.05
HORIZON_S = 24 * 3600
SNAPSHOT_READY_S = 23 * 3600

LIQUIDITY_FAIL = 25_000
LIQUIDITY_WARN = 50_000
LP_LOCK_FAIL_BELOW = 80
TOP10_WARN_ABOVE = 25
LARGEST_WARN_ABOVE = 15
CREATOR_WARN_ABOVE = 5
DEV_SOLD_WARN_ABOVE = 50
LAUNCHES_WARN_AT = 3
BUNDLE_FAIL_AT = 5
HONEYPOT_BUYS_ABOVE = 10
WASH_RATIO_ABOVE = 30
WASH_TRADERS_BELOW = 100
TOO_NEW_S = 180
MAX_AGE_S = 48 * 3600
NA_UNKNOWN_ABOVE = 4
WARN_VERDICT_AT = 3
CANDIDATE_CAP = 30
STALE_MS = 60 * 60 * 1000


def plan_dict():
    return {
        "entry": "t0 price",
        "stop_pct": -STOP_PCT,
        "tp1_pct": TP1_PCT,
        "tp1_sell_fraction": TP1_FRACTION,
        "trail_from_peak": TRAIL,
        "dead_after_s": DEAD_AFTER_S,
        "dead_if_gain_below": DEAD_BELOW_GAIN,
        "slippage_per_side": SLIPPAGE,
        "fee_per_side": FEE,
        "horizon_s": HORIZON_S,
    }
