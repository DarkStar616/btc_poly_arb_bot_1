import numpy as np
import warnings
from typing import Optional, Tuple

class TradeRingBuffer:
    def __init__(self, capacity: int = 100000):
        self.capacity = capacity
        # Columns: [ts_ms, price, qty, is_buyer_maker(0/1)]
        self.data = np.zeros((capacity, 4), dtype=np.float64)
        self.idx = 0
        self.size = 0
        self.full = False

    def add(self, ts_ms: float, price: float, qty: float, is_buyer_maker: bool):
        self.data[self.idx] = [ts_ms, price, qty, 1.0 if is_buyer_maker else 0.0]
        self.idx = (self.idx + 1) % self.capacity
        if not self.full and self.idx == 0:
            self.full = True
            self.size = self.capacity
        if not self.full:
            self.size = self.idx

    def get_trades(self, lookback_ms: float, current_ts_ms: float) -> np.ndarray:
        """Get trades falling within [current_ts_ms - lookback_ms, current_ts_ms]."""
        # Optimized for recent trades, we scan backwards or just use masking if not too large.
        # Since ring buffer wraps, slicing is tricky. We'll return a view or copy.
        # For simplicity in python: gather linear array first? Or just mask.
        
        cutoff = current_ts_ms - lookback_ms
        
        # Construct linear view for vectorized search
        if self.full:
            # Reorder: oldest to newest [idx:] + [:idx]
            linear = np.concatenate((self.data[self.idx:], self.data[:self.idx]))
        else:
            linear = self.data[:self.idx]

        # Filter
        # Assuming sorted by TS roughly, but network jitter might violate strict order.
        # We just filter by TS column (index 0).
        mask = linear[:, 0] >= cutoff
        return linear[mask]

    def clear(self):
        self.idx = 0
        self.size = 0
        self.full = False
