import logging
from dataclasses import dataclass
from typing import Optional

from ..timeutil import now_ts
from .gates import check_entry_gates
from .sizing import get_size_usd

@dataclass
class Signal:
    direction: str # UP, DOWN
    confidence: float
    edge: float
    size_usd: float
    meta: dict

class Zero8dxdStrategy:
    def __init__(self, config, health_mgr):
        self.config = config
        self.health = health_mgr
        self.logger = logging.getLogger("strategy")

    def on_tick(self, features, yes_book, no_book, account_state):
        """
        Main strategy loop tick.
        features: Binance Features
        yes_book, no_book: OrderBook
        account_state: dict (capital, position)
        """
        # 1. Gates
        # Calc virtual spread
        try:
             # Basic spread logic: min(spread_yes, spread_no)?
             # Or implied prob spread?
             # For simpler mvp: just check spread of the active token we might want to buy.
             # We assume we buy one of them.
             pass
        except:
             pass

        # 2. Logic
        # Thresholds
        mom_thresh = 0.0005 # 5bps return in 30s? Config check?
        
        # UP Signal
        is_up = features.ret_30s > mom_thresh
        is_down = features.ret_30s < -mom_thresh
        
        if not is_up and not is_down:
            return None # No signal

        # 3. Prob Mapping (Naive)
        # If UP, true_prob > 0.60?
        # If DOWN, true_prob for YES < 0.40? 
        # Let's say:
        # Base = 0.50
        # Impact = ret_30s * 100? -> 0.001 * 100 = 0.10 -> 0.60
        true_prob = 0.50 + (features.ret_30s * 50) # Scaling factor K
        true_prob = max(0.05, min(0.95, true_prob))

        # 4. Market Price
        # IF UP, we want to BUY YES. Market Prob = YES Ask.
        # IF DOWN, we want to BUY NO. Market Prob = NO Ask.
        
        target_token = "YES" if is_up else "NO"
        target_book = yes_book if target_token == "YES" else no_book
        
        if target_book.is_empty():
            return None

        _, best_ask = target_book.get_best()
        if best_ask <= 0 or best_ask >= 1:
            return None

        market_prob = best_ask
        
        # Edge = True - Market
        edge = true_prob - market_prob
        
        # Net Edge = Edge - Costs
        # cost ~ slippage + fees + spread/2 (already in ask vs mid)
        # spread cost is paid on entry (ask-mid) and exit (mid-bid)
        # Using Ask captures half the spread cost if we compare to Mid, 
        # but here we compare to "True Fair".
        # If "True Fair" is mid-based, then paying Ask implies paying spread/2.
        # Let's subtract explicit costs:
        costs_bps = self.config.taker_fee_bps + (self.config.max_slippage_bps/2) # estimate
        edge_net = edge - (costs_bps / 10000)

        if edge_net < self.config.edge_entry_min:
            return None

        # 5. Check Entry Gates
        # Calc spread BPS for target book
        bb, ba = target_book.get_best()
        spread_bps = ((ba - bb) / ba) * 10000 if ba > 0 else 9999
        
        allowed, reason = check_entry_gates(self.health, spread_bps, self.config.max_spread_bps)
        if not allowed:
            # Log gated?
            return None

        # 6. Size
        size = get_size_usd(account_state['capital'], self.config.risk_fraction, self.config.max_trade_usd)

        return Signal(
            direction="UP" if is_up else "DOWN",
            confidence=true_prob,
            edge=edge_net,
            size_usd=size,
            meta={'spread_bps': spread_bps, 'market_prob': market_prob}
        )
