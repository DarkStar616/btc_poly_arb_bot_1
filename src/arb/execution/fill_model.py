from typing import Tuple, Optional
from ..polymarket.orderbook import OrderBook

def simulate_market_order(book: OrderBook, side: str, size_usd: float, max_slippage_bps: int) -> Tuple[float, float, float, str]:
    """
    Simulate params:
    book: OrderBook
    side: 'BUY' or 'SELL'
    size_usd: Notional amount
    
    Returns: (fill_price, shares, slippage_usd, reason_code)
         fill_price=0 if failure.
    """
    if book.is_empty() or book.is_crossed():
         return 0.0, 0.0, 0.0, "BOOK_UNHEALTHY"

    try:
        vwap, shares = book.get_vwap_for_size(side, size_usd)
    except ValueError:
        return 0.0, 0.0, 0.0, "INSUFFICIENT_LIQUIDITY"

    if shares == 0:
        return 0.0, 0.0, 0.0, "ZERO_SHARES"

    # Calc slippage
    # Slippage = |VWAP - BestPrice| / BestPrice
    # BestPrice: Ask if Buy, Bid if Sell
    best_bid, best_ask = book.get_best()
    ref_price = best_ask if side == 'BUY' else best_bid
    
    if ref_price <= 0:
         return 0.0, 0.0, 0.0, "BAD_REF_PRICE"
         
    actual_diff = abs(vwap - ref_price)
    slip_bps = (actual_diff / ref_price) * 10000
    
    if slip_bps > max_slippage_bps:
        return 0.0, 0.0, 0.0, f"SLIPPAGE_HIGH_{int(slip_bps)}"
        
    slippage_usd = actual_diff * shares
    
    return vwap, shares, slippage_usd, "OK"
