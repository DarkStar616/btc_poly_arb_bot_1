from enum import Enum
from dataclasses import dataclass, field
from typing import Set, Optional, Dict, List
import logging
from .timeutil import now_ts

class BotState(Enum):
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"

class Gate(Enum):
    # Stopped Triggers
    INVARIANT_FAIL = "INVARIANT_FAIL"
    AUTH_FAIL = "AUTH_FAIL"
    
    # Paused Triggers
    STALE_FEED_BINANCE = "STALE_FEED_BINANCE"
    STALE_FEED_POLY = "STALE_FEED_POLY"
    BOOK_DESYNC = "BOOK_DESYNC"
    MARKET_AMBIGUOUS = "MARKET_AMBIGUOUS"
    MANUAL_PAUSE = "MANUAL_PAUSE"

    # Running but Gated (No Entry)
    SPREAD_HIGH = "SPREAD_HIGH"
    LIQUIDITY_LOW = "LIQUIDITY_LOW"
    VOLATILITY_HIGH = "VOLATILITY_HIGH"

@dataclass
class HealthStatus:
    state: BotState = BotState.RUNNING
    active_gates: Set[Gate] = field(default_factory=set)
    poly_lag_ms: float = 0.0
    binance_lag_ms: float = 0.0
    last_update_ts: float = 0.0

class BotHealth:
    def __init__(self, config):
        self.config = config
        self.status = HealthStatus(last_update_ts=now_ts())
        self.logger = logging.getLogger("health")

    def update_lag(self, source: str, lag_ms: float):
        if source == "poly":
            self.status.poly_lag_ms = lag_ms
            if lag_ms > self.config.health.poly_max_age_ms:
                self.set_gate(Gate.STALE_FEED_POLY)
            else:
                self.clear_gate(Gate.STALE_FEED_POLY)
        elif source == "binance":
            self.status.binance_lag_ms = lag_ms
            if lag_ms > self.config.health.binance_max_age_ms:
                self.set_gate(Gate.STALE_FEED_BINANCE)
            else:
                self.clear_gate(Gate.STALE_FEED_BINANCE)

    def set_gate(self, gate: Gate):
        if gate not in self.status.active_gates:
            self.logger.warning(f"Map Gate Triggered: {gate.value}")
            self.status.active_gates.add(gate)
            self._update_state()

    def clear_gate(self, gate: Gate):
        if gate in self.status.active_gates:
            self.logger.info(f"Map Gate Cleared: {gate.value}")
            self.status.active_gates.remove(gate)
            self._update_state()

    def _update_state(self):
        # Determine state based on gates
        stopped_gates = {Gate.INVARIANT_FAIL, Gate.AUTH_FAIL}
        paused_gates = {
            Gate.STALE_FEED_BINANCE, Gate.STALE_FEED_POLY, 
            Gate.BOOK_DESYNC, Gate.MARKET_AMBIGUOUS, Gate.MANUAL_PAUSE
        }

        if self.status.active_gates.intersection(stopped_gates):
            self.status.state = BotState.STOPPED
        elif self.status.active_gates.intersection(paused_gates):
            self.status.state = BotState.PAUSED
        else:
            self.status.state = BotState.RUNNING

    def check_pnl_invariant(self, equity: float, cash: float, unrealized: float, tolerance: float = 0.01):
        # equity = cash + unrealized
        diff = abs(equity - (cash + unrealized))
        if diff > tolerance:
            msg = f"PnL Invariant Failed: Eq={equity} != Cash={cash} + Unreal={unrealized} (Diff={diff})"
            self.logger.critical(msg)
            self.set_gate(Gate.INVARIANT_FAIL)
            raise RuntimeError(msg)

    def is_runnable(self) -> bool:
        return self.status.state == BotState.RUNNING
