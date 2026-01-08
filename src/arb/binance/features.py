import numpy as np
from dataclasses import dataclass
from ..timeutil import now_ts

@dataclass
class Features:
    ret_5s: float = 0.0
    ret_15s: float = 0.0
    ret_30s: float = 0.0
    vol_ratio: float = 1.0 # vol_fast / vol_slow
    trade_count_10s: int = 0
    valid: bool = False

def compute_features(rb, now_ms: float) -> Features:
    # rb is TradeRingBuffer
    # features: returns (log or pct), counts, vol
    
    # 30s lookback
    trades = rb.get_trades(30000, now_ms)
    
    if len(trades) < 2:
        return Features(valid=False)

    # Sort by time just in case (though RB usually sorted)
    # trades columns: [ts, price, qty, maker]
    # trades is np array
    
    times = trades[:, 0]
    prices = trades[:, 1]
    
    current_price = prices[-1]

    # Helper to find price N seconds ago
    def get_past_price(ms_ago):
        target = now_ms - ms_ago
        # Find index where time >= target
        # Search sorted?
        idx = np.searchsorted(times, target)
        if idx < len(prices):
            return prices[idx]
        return prices[0] # Fallback to oldest

    p_5s = get_past_price(5000)
    p_15s = get_past_price(15000)
    p_30s = get_past_price(30000)

    # Log returns usually, but pct is fine for short windows
    fns = lambda p0, p1: (p1/p0 - 1.0) if p0 > 0 else 0.0
    
    ret_5s = fns(p_5s, current_price)
    ret_15s = fns(p_15s, current_price)
    ret_30s = fns(p_30s, current_price)

    # Volatility proxy
    # Std dev of returns in last 30s vs last 120s? 
    # Or simplified: range over mean?
    # Let's do std of price changes in last 10s (fast) vs 60s (slow)
    # Needs more data. RB has 120s?
    
    # Simple count
    count_10s = np.sum(times >= (now_ms - 10000))

    return Features(
        ret_5s=ret_5s,
        ret_15s=ret_15s,
        ret_30s=ret_30s,
        vol_ratio=1.0, # Placeholder for now to keep simple
        trade_count_10s=int(count_10s),
        valid=True
    )
