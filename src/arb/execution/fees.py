from dataclasses import dataclass

@dataclass
class FeeSchedule:
    maker_bps: int = 0
    taker_bps: int = 0

def calc_fees(size_usd: float, fee_bps: int) -> float:
    return size_usd * (fee_bps / 10000.0)
