import asyncio
import json
import logging
import websockets
import random
from typing import Optional, Callable, Awaitable
from ..timeutil import now_ts

class BinanceWsClient:
    def __init__(self, url: str, symbol: str, 
                 ring_buffer, 
                 health_mgr,
                 logger):
        self.url = f"{url}/{symbol}@aggTrade"
        self.symbol = symbol
        self.rb = ring_buffer
        self.health = health_mgr
        self.logger = logger
        self.running = False
        self.ws = None
        self.last_msg_ts = 0.0
        self.reconnect_delay = 1.0

    async def start(self):
        self.running = True
        while self.running:
            try:
                self.logger.info(f"Connecting to Binance WS: {self.url}")
                async with websockets.connect(self.url) as ws:
                    self.ws = ws
                    self.last_msg_ts = now_ts()
                    self.health.update_lag("binance", 0)
                    self.reconnect_delay = 1.0 # Reset backoff

                    while self.running:
                        try:
                            # Wait for message with timeout for heartbeat check
                            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                            self._handle_msg(msg)
                        except asyncio.TimeoutError:
                            # Check if we should ping or just loop
                            lag = (now_ts() - self.last_msg_ts) * 1000
                            self.health.update_lag("binance", lag)
                            # If lag is too high, health mgr triggers STALE_FEED -> Logic elsewhere handles pause
                            # But here we might want to proactively reconnect if truly dead
                            if lag > 10000: # 10s silent
                                self.logger.warning("Binance WS silent > 10s. Reconnecting.")
                                await ws.close()
                                break
                        except websockets.ConnectionClosed:
                            self.logger.warning("Binance WS Connection Closed.")
                            break
            except Exception as e:
                self.logger.error(f"Binance WS Error: {e}")
                self.health.set_gate(self.health.config.Gate.STALE_FEED_BINANCE) # Force stale on error
            
            if self.running:
                # Backoff
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(self.reconnect_delay * 1.5, 30.0)

    def _handle_msg(self, msg: str):
        ts = now_ts()
        try:
            data = json.loads(msg)
            # data spec: {e: aggTrade, E: event_time, s: symbol, p: price, q: quantity, m: is_buyer_maker, ...}
            if data.get('e') == 'aggTrade':
                event_ts = data['E'] # ms
                price = float(data['p'])
                qty = float(data['q'])
                is_maker = data['m']
                
                # Push to RB
                self.rb.add(event_ts, price, qty, is_maker)
                
                # Update Health
                self.last_msg_ts = ts
                
                # Lag computation: Now(ms) - Event(ms). 
                # Note: System clock vs Exchange clock skew is real. 
                # Ideally we want inter-arrival gap or just freshness.
                # using local recv time for freshness mainly.
                self.health.update_lag("binance", (ts * 1000) - event_ts)
                
                # Log Raw (if configured, we usually write raw logs in the wrapper/main loop or here if we pass logger)
                # Assuming raw logger is available in self.logger
                if hasattr(self.logger, 'log_raw_binance'):
                    self.logger.log_raw_binance(data)

        except Exception as e:
            self.logger.error(f"Binance Decode Error: {e}")

    async def stop(self):
        self.running = False
        if self.ws:
            await self.ws.close()
