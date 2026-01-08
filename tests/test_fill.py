import pytest
from src.arb.polymarket.orderbook import OrderBook
from src.arb.execution.fill_model import simulate_market_order

def test_vwap_sweeps():
    book = OrderBook("TEST")
    # Asks: 0.50 (100), 0.60 (100)
    book.update([
        {'side': 'SELL', 'price': 0.50, 'size': 100},
        {'side': 'SELL', 'price': 0.60, 'size': 100}
    ])
    
    # Buy $25 worth. Should fill at 0.50.
    # $25 / 0.50 = 50 shares.
    vwap, shares, slip, reason = simulate_market_order(book, 'BUY', 25.0, 100)
    assert reason == "OK"
    assert vwap == 0.50
    assert shares == 50.0

    # Buy $75 worth. Should fill 100 shares at 0.50 ($50) + remainder ($25) at 0.60.
    # Remainder shares = 25 / 0.60 = 41.666
    # Total shares = 141.666
    # Total cost = 75.
    # Expected VWAP = 75 / 141.666 = 0.529
    vwap, shares, slip, reason = simulate_market_order(book, 'BUY', 75.0, 5000) # high slip tol
    assert reason == "OK"
    assert shares > 141.6
    assert 0.52 < vwap < 0.54

def test_too_large_rejection():
    book = OrderBook("TEST")
    book.update([{'side': 'SELL', 'price': 0.50, 'size': 10}]) # only $5 depth
    
    # Try buy $100
    vwap, shares, slip, reason = simulate_market_order(book, 'BUY', 100.0, 100)
    assert reason == "INSUFFICIENT_LIQUIDITY"
    assert shares == 0
