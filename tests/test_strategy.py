import pytest
from src.arb.strategy.gates import check_entry_gates
from src.arb.strategy.exits import check_exits, ExitResult
from src.arb.health import BotHealth, Gate
from src.arb.execution.paper_broker import Position

class MockConfig:
    class strategy:
        tp_bps = 100
        sl_bps = 50
        max_hold_sec = 100
        edge_exit_min = 0.02
    class health:
        class state:
             RUNNING = "RUNNING"
             
def test_exit_logic():
    cfg = MockConfig()
    # Entry at 0.50, Cost 100. 200 shares.
    pos = Position(
        token_id="YES", direction="UP", shares=200, 
        avg_entry=0.50, cost_usd=100.0, entry_ts=1000, entry_edge=0.10
    )
    
    # 1. No exit
    res = check_exits(pos, 0.50, 0.10, 0.10, 1010, cfg.strategy)
    assert not res.should_exit

    # 2. TP (+100bps -> 1%)
    # Gain $1. Exit Value 101. Price = 101/200 = 0.505.
    res = check_exits(pos, 0.506, 0.10, 0.10, 1010, cfg.strategy)
    assert res.should_exit
    assert res.reason == "TP"

    # 3. SL (-50bps -> -0.5%)
    # Loss $0.5. Exit Value 99.5. Price = 99.5/200 = 0.4975
    res = check_exits(pos, 0.497, 0.10, 0.10, 1010, cfg.strategy)
    assert res.should_exit
    assert res.reason == "SL"
