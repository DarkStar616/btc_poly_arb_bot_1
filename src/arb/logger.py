import logging
import json
import csv
import os
from datetime import datetime
from typing import Any, Dict, Optional
from .timeutil import now_ts, now_iso

class ServiceLogger:
    def __init__(self, run_id: str, log_dir: str):
        self.run_id = run_id
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)

        self.jsonl_path = os.path.join(log_dir, f"run_{run_id}.jsonl")
        self.trades_path = os.path.join(log_dir, f"trades_{run_id}.csv")
        self.pnl_path = os.path.join(log_dir, f"pnl_{run_id}.csv")
        
        # Raw logs
        self.raw_binance_path = os.path.join(log_dir, f"raw_binance_{run_id}.jsonl")
        self.raw_poly_path = os.path.join(log_dir, f"raw_poly_{run_id}.jsonl")

        self.setup_logging()
        self._init_csv_headers()

    def setup_logging(self):
        # Initialize file handlers
        self.jsonl_File = open(self.jsonl_path, 'a', encoding='utf-8')
        self.raw_binance_file = open(self.raw_binance_path, 'a', encoding='utf-8')
        self.raw_poly_file = open(self.raw_poly_path, 'a', encoding='utf-8')

    def _init_csv_headers(self):
        # Trades CSV
        with open(self.trades_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'entry_ts', 'exit_ts', 'direction', 'token_id', 'size_usd', 
                'entry_price', 'exit_price', 'pnl_usd', 'pnl_bps', 'exit_reason',
                'entry_edge', 'entry_spread_bps', 'fees_usd', 'slippage_usd'
            ])
        
        # PnL CSV
        with open(self.pnl_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'equity', 'cash', 'unrealized_pnl', 'realized_pnl', 'drawdown_pct'])

    def log_event(self, event_type: str, data: Dict[str, Any]):
        event = {
            'ts': now_ts(),
            'iso': now_iso(),
            'type': event_type,
            'data': data
        }
        self.jsonl_File.write(json.dumps(event) + '\n')
        self.jsonl_File.flush()

    def log_trade_completion(self, trade: Dict[str, Any]):
        """Append a resolved trade to the CSV."""
        with open(self.trades_path, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                trade.get('entry_ts'),
                trade.get('exit_ts'),
                trade.get('direction'),
                trade.get('token_id'),
                trade.get('size_usd'),
                trade.get('entry_fill'),
                trade.get('exit_fill'),
                trade.get('pnl_usd'),
                trade.get('pnl_bps'),
                trade.get('exit_reason'),
                trade.get('entry_edge'),
                trade.get('entry_spread_bps'),
                trade.get('fees_usd'),
                trade.get('slippage_usd')
            ])
        self.log_event("trade_complete", trade)

    def log_pnl_snapshot(self, equity: float, cash: float, unrealized: float, realized: float, dd: float):
        row = [now_iso(), equity, cash, unrealized, realized, dd]
        with open(self.pnl_path, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(row)
        # Also log as event for visibility
        self.log_event("pnl_snapshot", {
            'equity': equity, 'unrealized': unrealized, 'realized': realized, 'dd': dd
        })

    def log_raw_binance(self, payload: Dict):
        self.raw_binance_file.write(json.dumps({'ts': now_ts(), 'msg': payload}) + '\n')
        # Buffer flush strategy could be optimized, but flushing typically for safety
        self.raw_binance_file.flush()

    def log_raw_poly(self, payload: Dict):
        self.raw_poly_file.write(json.dumps({'ts': now_ts(), 'msg': payload}) + '\n')
        self.raw_poly_file.flush()

    def close(self):
        self.jsonl_File.close()
        self.raw_binance_file.close()
        self.raw_poly_file.close()
