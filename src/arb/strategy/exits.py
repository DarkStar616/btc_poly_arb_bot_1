from dataclasses import dataclass
from typing import Optional

@dataclass
class ExitResult:
    should_exit: bool
    reason: str = ""

def check_exits(position, current_bid, entry_edge, current_edge, current_ts, config) -> ExitResult:
    """
    Check for TP, SL, Time Stop, Edge Collapse.
    position: PaperPosition
    current_bid: float (Mark to Market price)
    """
    if not position:
        return ExitResult(False)

    # Calculate PnL BPS
    # PnL = (exit - entry) / entry? No, (exit_val - entry_cost) / entry_cost usually for ROI
    # value = shares * bid
    # pnl = value - cost
    # bps = (pnl / cost) * 10000
    
    cost = position.cost_usd
    if cost <= 0: return ExitResult(False) # Should not happen

    mtm_value = position.shares * current_bid
    pnl_usd = mtm_value - cost
    pnl_bps = (pnl_usd / cost) * 10000

    # 1. Edge Collapse
    if current_edge < config.edge_exit_min:
         return ExitResult(True, "EDGE_COLLAPSE")

    # 2. TP
    if pnl_bps >= config.tp_bps:
        return ExitResult(True, "TP")

    # 3. SL
    if pnl_bps <= -config.sl_bps:
        return ExitResult(True, "SL")

    # 4. Time Stop
    hold_sec = current_ts - position.entry_ts
    if hold_sec >= config.max_hold_sec:
         return ExitResult(True, "TIME_STOP")
         
    return ExitResult(False)
