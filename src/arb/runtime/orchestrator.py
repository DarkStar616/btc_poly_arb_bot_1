import asyncio
import logging
from typing import Optional
from dataclasses import asdict

from ..config import Config
from ..logger import ServiceLogger
from ..health import BotHealth, Gate, BotState
from ..timeutil import now_ts, format_delta_ms

from ..binance.ws_aggtrade import BinanceWsClient
from ..binance.ringbuffer import TradeRingBuffer
from ..binance.features import compute_features

from ..polymarket.gamma_client import GammaClient
from ..polymarket.market_selector import MarketSelector
from ..polymarket.clob_ws import ClobWsClient
from ..polymarket.orderbook import OrderBook

from ..strategy.zero8dxd_live import Zero8dxdStrategy
from ..execution.paper_broker import PaperBroker
from ..execution.fill_model import simulate_market_order
from ..execution.fees import calc_fees # Actually broker uses it, maybe Orchestrator too?

class Orchestrator:
    def __init__(self, config: Config, run_id: str, ui_queue: Optional[asyncio.Queue] = None):
        self.config = config
        self.run_id = run_id
        self.ui_queue = ui_queue
        
        # Core
        self.health = BotHealth(config)
        self.data_logger = ServiceLogger(run_id, config.system.log_dir) # Reserved for raw data/events
        self.logger = logging.getLogger("orch") # Operational Logs
        
        # Data
        self.rb = TradeRingBuffer()
        self.gamma = GammaClient(config.endpoints)
        self.selector = MarketSelector(config)
        
        # State
        self.current_market: Optional[dict] = None
        self.current_books = {} # token_id -> OrderBook
        self.token_map = {} # YES/NO -> token_id
        
        # Clients
        self.binance_ws = BinanceWsClient(
            config.endpoints.binance_ws, 
            config.market.binance_symbol, 
            self.rb, self.health, self.data_logger
        )
        self.clob_ws: Optional[ClobWsClient] = None
        
        # Strategy/Broker
        self.strategy = Zero8dxdStrategy(config.strategy, self.health)
        self.broker = PaperBroker(config, self.health, self.logger)

        self.running = False
        self.tasks = []

    async def run(self):
        self.running = True
        self.console.info(f"Starting Run {self.run_id}. Waiting for active market...")

        # Start Binance (Always on)
        self.tasks.append(asyncio.create_task(self.binance_ws.start()))
        # Start Resync Loop
        self.tasks.append(asyncio.create_task(self._resync_loop()))

        while self.running:
            # 1. Discovery / Rollover Loop
            if not self.current_market:
                await self._find_and_subscribe_market()
                if not self.current_market:
                    await asyncio.sleep(5)
                    continue

            # 2. Monitor Expiry
            # Check if current market expired
            # We used ISO string sort in selector.
            # Here we parse properly or just re-check active status periodically?
            # Better: Monitor time remaining.
            
            # 3. Tick Loop (Fast)
            # Run for X seconds or until expiry?
            # Let's run a tick loop, breaking if market invalid
            await self._tick_loop()
            
            # If tick loop exits, it means market expired or forced restart
            # Close/Settle
            await self._handle_market_end()

    async def _find_and_subscribe_market(self):
        retry_count = 0
        max_retries = 10
        
        from datetime import datetime, timezone, timedelta
        
        while not self.current_market and self.running:
            try:
                # Robust Time Params
                # start_date_min = now - 45 min
                # start_date_max = now + 10 min
                # end_date_min = now - 10 min
                # end_date_max = now + 45 min
                now = datetime.now(timezone.utc)
                
                params = {
                    "limit": 100, # Large limit
                    "closed": "false",
                    "order": "startDate", # Order by creation usually best to find new markets
                    "ascending": "false",
                    # Time Window
                    "start_date_min": (now - timedelta(minutes=45)).isoformat(),
                    "start_date_max": (now + timedelta(minutes=10)).isoformat(),
                    # "end_date_min": (now - timedelta(minutes=10)).isoformat(), # Optional
                    # "end_date_max": (now + timedelta(minutes=45)).isoformat()
                }

                if retry_count > 3:
                     # Widen window
                     params["limit"] = 200
                     params["start_date_min"] = (now - timedelta(hours=3)).isoformat()

                markets = self.gamma.search_markets(params)
                
                selected = self.selector.select_active_market(markets)
                
                if selected:
                    self.current_market = selected
                    m = selected['market']
                    tmap = selected['token_map']
                    self.token_map = tmap
                    
                    self.console.info(f"Market Selected: {m.get('question', 'Unknown')}")
                    self.console.info(f"  ID: {m.get('id')}")
                    self.console.info(f"  Slug: {m.get('slug')}")
                    self.console.info(f"  Map: {tmap}")
                    self.console.info(f"  Exp: {selected.get('end_iso')}")
                    self.console.info(f"  Now (UTC): {now.isoformat()}")
                    
                    # Init Books
                    self.current_books = {
                        tmap['YES']: OrderBook(tmap['YES']),
                        tmap['NO']: OrderBook(tmap['NO'])
                    }
                    
                    # Start CLOB WS
                    import logging
                    self.clob_ws = ClobWsClient(
                        self.config.endpoints.poly_ws,
                        self.current_books,
                        self.health,
                        self.config.auth,
                        logger=logging.getLogger("clob_ws"),
                        service_logger=self.data_logger
                    )
                    self.tasks.append(asyncio.create_task(self._safe_task(self.clob_ws.start(), "clob_ws")))
                    return
                    
                else:
                    retry_count += 1
                    # Diagnostics
                    if retry_count > max_retries:
                         self.logger.error("Max retries reached. Discovery failed.")
                         self.logger.error(f"Last Params: {params}")
                         self.logger.error(f"Sample Candidates (Top 5/{len(markets)}):")
                         for cand in markets[:5]:
                             self.logger.error(f"  {cand.get('slug')} | {cand.get('startDate')} -> {cand.get('endDate')}")
                         self.running = False
                         return

                    wait = 2.0
                    self.logger.warning(f"No active market. Retrying in {wait}s... (Count {retry_count})")
                    await asyncio.sleep(wait)

            except Exception as e:
                self.logger.error(f"Discovery Error: {e}")
                await asyncio.sleep(5)

    async def _tick_loop(self):
        ticker_interval = 0.1 # 100ms
        while self.running and self.current_market:
             # Check Health Invariants
             # self.health.check_pnl_invariant(...) # Needs args
             
             # Features
             now = now_ts()
             feats = compute_features(self.rb, now * 1000)
             
             # Books
             yes_book = self.current_books[self.token_map['YES']]
             no_book = self.current_books[self.token_map['NO']]
             
             # Account State
             acct = self.broker.get_state()
             
             # Strategy Signal (Only if Healthy/Running)
             if self.health.is_runnable():
                try:
                    signal = self.strategy.on_tick(feats, yes_book, no_book, acct)
                    if signal:
                        self.process_signal(signal, yes_book, no_book)
                except Exception as e:
                    self.logger.error(f"Strategy Error: {e}", exc_info=True)
                    self.health.set_gate(Gate.MANUAL_PAUSE) # Pause on strategy error

             # Exits
             if self.broker.position:
                 pos = self.broker.position
                 # Get current exit price (Bid)
                 # Determine token book
                 # Map YES/NO to book?
                 # pos.token_id is "YES" or "NO"
                 # Wait, Position stored "YES"/"NO" string? or clobID?
                 # PaperBroker: token_id="YES" if signal.direction == "UP" else "NO"
                 # Yes.
                 pos_token_str = pos.token_id
                 pos_book = yes_book if pos_token_str == "YES" else no_book
                 
                 curr_bid, _ = pos_book.get_best()
                 
                 # Calc Edge (optional for exit)
                 # Exit model needs edge? Yes, "Edge Collapse"
                 # We can re-run strategy logic or just pass 0 if lazy?
                 # Let's pass 0 for now or approx
                 curr_edge = 0.0 # Placeholder
                 
                 from ..strategy.exits import check_exits
                 exit_res = check_exits(pos, curr_bid, pos.entry_edge, curr_edge, now, self.config.strategy)
                 
                 if exit_res.should_exit:
                      self.process_exit(pos_book, pos, exit_res.reason)

             # UI Update
             if self.ui_queue and not self.ui_queue.full():
                 snap = {
                     'ts': now,
                     'health': asdict(self.health.status), # Enum serialization might fail? convert to str
                     'market': self.current_market['market']['question'],
                     'btc_price': feats.ret_5s, # Misusing field? No, feature doesn't store price.
                     # We need price.
                     'features': asdict(feats),
                     'book_yes': yes_book.get_best(),
                     'book_no': no_book.get_best(),
                     'account': str(acct) # Simplify
                 }
                 # Hack: manually add active gates string
                 snap['gates'] = [g.value for g in self.health.status.active_gates]
                 snap['state'] = self.health.status.state.value
                 self.ui_queue.put_nowait(snap)
                 
             # Check Market Expiry Time
             # Parse endDate
             end_iso = self.current_market['end_iso'] # Z format
             # Convert to TS
             # Quick hack: If we see "Resolved" in Gamma polling?
             # For now, simplistic time check:
             # If "Now" > EndDate, break
             # ...
             
             await asyncio.sleep(ticker_interval)

    def process_signal(self, signal, yes_book, no_book):
        # Direction UP -> Buy YES
        book = yes_book if signal.direction == "UP" else no_book
        
        # Fill
        vwap, shares, slip_usd, reason = simulate_market_order(
            book, 'BUY', signal.size_usd, self.config.strategy.max_slippage_bps
        )
        
        if reason != "OK":
            self.console.warning(f"Entry Rejected: {reason}")
            return
            
        fees = calc_fees(signal.size_usd, self.config.strategy.taker_fee_bps)
        self.broker.execute_entry(signal, vwap, shares, fees, slip_usd)

    def process_exit(self, book, position, reason):
        # Exit = SELL
        # Size? "Shares"
        # Since fill model takes USD size usually...
        # Wait, get_vwap_for_size takes "size_usd".
        # If we sell Shares, we need to know approx value?
        # Or update fill model to take shares?
        # fill_model: simulate_market_order(book, side, size_usd, ...)
        # We need to adapt fill model to 'Sell Shares' or convert shares to USD approx?
        # Value ~ Shares * Bid.
        est_value = position.shares * book.get_best()[0]
        
        vwap, shares_filled, slip_usd, code = simulate_market_order(
            book, 'SELL', est_value, self.config.strategy.max_slippage_bps
        )
        
        # If partial fill or rejection on exit?
        # Make aggressive?
        if code != "OK":
            self.console.warning(f"Exit Rejected ({reason}): {code}. Forcing mid?")
            # Force exit at bid?
            vwap = book.get_best()[0]
            if vwap <= 0: vwap = 0.01 # Disaster
            
        fees = calc_fees(est_value, self.config.strategy.taker_fee_bps)
        self.broker.execute_exit(vwap, reason, fees, slip_usd)

    async def _handle_market_end(self):
        self.console.info("Market Ended/Expired.")
        # Stop CLOB WS
        if self.clob_ws:
            await self.clob_ws.stop()
            self.clob_ws = None
        
        # Force Exit Position if open
        if self.broker.position:
             # Assume settlement price?
             # If resolved, use 1.0 or 0.0.
             # If not resolved yet, we force exit at 0? Or last bid?
             # "EXPIRY_FORCE_EXIT" -> use last known bid probably 0 if market closed.
             self.broker.execute_exit(0.0, "EXPIRY_SETTLEMENT", 0, 0) # Conservative 0
            
        self.current_market = None
        self.current_books = {}

    async def _resync_loop(self):
        """Periodically refresh books from REST snapshot to prevent delta drift."""
        while self.running:
            if self.current_market and self.current_books:
                try:
                    for tid, book in self.current_books.items():
                        snap = await self._fetch_clob_snapshot(tid)
                        if snap:
                            # 1. Check Drift before resync
                            self._check_desync(book, snap)
                            # 2. Resync
                            book.resync_with_snapshot(snap['bids'], snap['asks'])
                except Exception as e:
                    self.console.error(f"Resync Loop Error: {e}")
            
            await asyncio.sleep(self.config.health.book_resync_interval_sec)

    async def _fetch_clob_snapshot(self, token_id: str) -> Optional[dict]:
        import requests
        url = f"{self.config.endpoints.clob_rest}/book?token_id={token_id}"
        try:
            # Need to run in executor or use aiohttp
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(None, lambda: requests.get(url, timeout=5))
            resp.raise_for_status()
            data = resp.json()
            
            # Format: {'bids': [['price', 'size'], ...], 'asks': ...}
            # Convert to Dict[float, float]
            res = {'bids': {}, 'asks': {}}
            for p, s in data.get('bids', []):
                res['bids'][float(p)] = float(s)
            for p, s in data.get('asks', []):
                res['asks'][float(p)] = float(s)
            return res
        except Exception as e:
            self.console.warning(f"Failed to fetch snapshot for {token_id}: {e}")
            return None

    def _check_desync(self, book: OrderBook, snap: dict):
        """Compare current book bests vs snapshot."""
        if book.is_empty(): return
        
        bb, ba = book.get_best()
        s_bb = max(snap['bids'].keys()) if snap['bids'] else 0.0
        s_ba = min(snap['asks'].keys()) if snap['asks'] else 0.0
        
        if s_bb <= 0 or s_ba <= 0: return # Invalid snap?
        
        # Deviation in BPS
        # (diff / snapshot_price) * 10000
        diff_bid = abs(bb - s_bb) / s_bb * 10000
        diff_ask = abs(ba - s_ba) / s_ba * 10000
        
        drift = max(diff_bid, diff_ask)
        
        if drift > self.config.health.snapshot_drift_bps:
            self.console.warning(f"BOOK_DESYNC Detected: Drift={drift:.1f} bps > {self.config.health.snapshot_drift_bps}")
            self.health.set_gate(Gate.BOOK_DESYNC)
        else:
            # If was desynced, maybe clear if drift is low?
            # Usually only clear after successful resync in orchestrated logic
            pass

    async def _safe_task(self, coro, name: str):
        try:
            await coro
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.critical(f"Task '{name}' Crashing: {e}", exc_info=True)
            self.health.set_gate(Gate.MANUAL_PAUSE)
            self.running = False 

    async def shutdown(self):
        self.running = False
        await self.binance_ws.stop()
        if self.clob_ws: await self.clob_ws.stop()
        self.logger.close()
