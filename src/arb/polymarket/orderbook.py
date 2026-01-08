from typing import Dict, List, Tuple, Optional
import sortedcontainers
import logging
from dataclasses import dataclass
from ..timeutil import now_ts

@dataclass
class FillOutcome:
    fill_price: float
    shares: float
    fees: float = 0.0
    slippage: float = 0.0
    reason: str = "OK"

class OrderBook:
    def __init__(self, token_id: str):
        self.token_id = token_id
        # Bids: Descending price
        self.bids = sortedcontainers.SortedDict(lambda x: -float(x)) 
        # Asks: Ascending price
        self.asks = sortedcontainers.SortedDict(lambda x: float(x))
        self.last_update_ts = now_ts()
        self.logger = logging.getLogger(f"book_{token_id}")

    def resync_with_snapshot(self, bids: Dict[float, float], asks: Dict[float, float]):
        """
        Replace entire book with a REST snapshot.
        """
        self.bids.clear()
        self.asks.clear()
        self.bids.update(bids)
        self.asks.update(asks)
        self.last_update_ts = now_ts()
        self.logger.info(f"Book Resynced: {len(bids)} bids, {len(asks)} asks")

    def update(self, changes: List[Dict]):
        """
        Apply delta updates.
        Change dict: {'side': 'BUY'/'SELL', 'price': '0.xyz', 'size': '100'}
        """
        self.last_update_ts = now_ts()
        for c in changes:
            try:
                side = c.get('side', '').upper()
                price = float(c.get('price', 0))
                size = float(c.get('size', 0))

                target = self.bids if side == 'BUY' else self.asks
                
                if size <= 1e-9: # Delete
                    if price in target:
                        del target[price]
                else:
                    target[price] = size
                    
            except Exception as e:
                self.logger.error(f"Book Update Error: {e} | {c}")

    def get_vwap_for_size(self, side: str, size_usd: float) -> Tuple[float, float]:
        """
        Calculate VWAP fill price for a market TAKING order of size_usd.
        side: 'BUY' (Take Asks) or 'SELL' (Hit Bids).
        Returns: (vwap_price, total_shares)
        Raises: ValueError if insufficient liquidity.
        """
        # If we BUY, we match against ASKS
        target_book = self.asks if side == 'BUY' else self.bids
        
        remaining_usd = size_usd
        total_shares = 0.0
        total_cost = 0.0

        # Walk the book
        for price, size in target_book.items():
            # For BUY (taking asks), price is cost per share.
            # For SELL (hitting bids), price is proceeds per share. (But here we define size_usd as VALUE traded usually?)
            # Wait, size_usd for ENTRY usually means "I want to spend $X".
            # For EXIT, "I want to sell Y shares".
            # Let's standardize: size_usd here implies Notional Value we want to transact?
            # Or is it "I want to buy shares worth $X"? -> typical for entry.
            # "I want to sell shares worth $X"? -> typical for exit? No, exit is usually quantity based.
            # This method signature says `size_usd`. Let's assume Entry-like logic: Fixed Notional.
            
            # Value of this level = price * size
            level_value = price * size
            
            if level_value >= remaining_usd:
                # Fill remainder here
                # shares = usd / price
                shares = remaining_usd / price
                total_shares += shares
                total_cost += remaining_usd
                remaining_usd = 0
                break
            else:
                # Consume level
                total_shares += size
                total_cost += level_value
                remaining_usd -= level_value

        if remaining_usd > 1e-4:
            raise ValueError(f"Insufficient Liquidity. Unfilled: ${remaining_usd}")

        if total_shares == 0:
             return 0.0, 0.0

        vwap = total_cost / total_shares
        return vwap, total_shares

    def get_best(self) -> Tuple[float, float]:
        """Return best_bid, best_ask."""
        bb = self.bids.peekitem(0)[0] if self.bids else 0.0
        ba = self.asks.peekitem(0)[0] if self.asks else 0.0
        return bb, ba

    def is_crossed(self) -> bool:
        bb, ba = self.get_best()
        return (bb > 0 and ba > 0) and (bb >= ba)

    def is_empty(self) -> bool:
        return not self.bids and not self.asks
