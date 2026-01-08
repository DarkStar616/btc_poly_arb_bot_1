import asyncio
import json
import logging
import websockets
from typing import Dict, List, Optional
from ..timeutil import now_ts
from .orderbook import OrderBook

class ClobWsClient:
    def __init__(self, url_base: str, 
                 books: Dict[str, OrderBook], 
                 health_mgr,
                 auth_config,
                 logger: logging.Logger,
                 service_logger=None):
        
        if not isinstance(logger, logging.Logger):
            # Guard to prevent silent failures
            raise ValueError("ClobWsClient Requires a standard logging.Logger instance.")
            
        self.url_base = url_base # "wss://ws-subscriptions-clob.polymarket.com/ws/market"
                                 # We will try variants based on this or hardcoded modes
        self.books = books
        self.health = health_mgr
        self.auth = auth_config
        self.logger = logger
        self.service_logger = service_logger
        self.running = False
        self.ws = None
        self.last_msg_ts = 0.0

    async def start(self):
        self.running = True
        
        # Dual Mode Endpoints
        # Mode 1: .../ws/market
        # Mode 2: .../ws/
        endpoints = [
            "wss://ws-subscriptions-clob.polymarket.com/ws/market",
            "wss://ws-subscriptions-clob.polymarket.com/ws/"
        ]
        
        ep_idx = 0
        
        while self.running:
            url = endpoints[ep_idx]
            try:
                self.logger.info(f"Connecting to Poly CLOB WS (Mode {ep_idx+1}): {url}")
                async with websockets.connect(url) as ws:
                    self.ws = ws
                    self.last_msg_ts = now_ts()
                    self.health.update_lag("poly", 0)
                    
                    self.logger.info(f"Poly WS Connected via Mode {ep_idx+1}.")
                    await self._subscribe(ws)
                    
                    pings = 0
                    pongs = 0
                    
                    while self.running:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                            if msg == "PING":
                                await ws.send("PONG")
                                pings += 1
                                continue
                            if msg == "PONG":
                                pongs += 1
                                continue
                                
                            self._handle_msg(msg)
                            self.last_msg_ts = now_ts()
                            
                            # Update health with counts periodically? 
                            # For now just update lag which implies activity.
                        
                        except asyncio.TimeoutError:
                            # Keep alive
                            try:
                                await ws.send("PING")
                            except:
                                break
                                
                        except websockets.ConnectionClosed:
                            self.logger.warning(f"Poly WS Closed ({url})")
                            break
                            
            except Exception as e:
                self.logger.error(f"Poly WS Error ({url}): {e}")
                self.health.set_gate(self.health.config.Gate.STALE_FEED_POLY)
                
                # Toggle Endpoint on failure
                ep_idx = (ep_idx + 1) % len(endpoints)
                await asyncio.sleep(2.0)
                
    async def _subscribe(self, ws):
        token_ids = list(self.books.keys())
        if not token_ids: return

        # User specified payload: {"type":"market","assets_ids":["..."]}
        payload = {
            "type": "market",
            "assets_ids": token_ids
        }
        
        self.logger.info(f"Subscribing with payload: {payload}")
        await ws.send(json.dumps(payload))

    def _handle_msg(self, msg: str):
        ts = now_ts()
        try:
            if not msg or msg in ('PONG', '1'):
                 return
            
            try:
                data = json.loads(msg)
            except json.JSONDecodeError:
                self.logger.warning(f"Poly WS Non-JSON Match: {msg!r}")
                return

            # Log Raw
            if self.service_logger:
                self.service_logger.log_raw_poly(data)

            # Handle Market Data
            # Format from "market" channel might differ from "level2"
            # It usually sends updates for the assets.
            # If it's the "market" structure, it might list updates.
            # We must be robust.
            
            items = data if isinstance(data, list) else [data]
            
            for item in items:
                # "market" channel usually uses "asset_id" or "token_id"?
                # or "event_type": "book"?
                # Let's support both standard L2 structure and implied new structure.
                
                tid = item.get('token_id') or item.get('asset_id')
                # If market channel sends PRICE updates (L1), we might get "price", "span", etc.
                # If we get Orderbook updates, look for "bids"/"asks" or "changes".
                
                if not tid:
                     # Maybe it's nested?
                     continue
                     
                if tid in self.books:
                    # Look for book updates
                    # Standard Poly format: 'changes' or 'bids'/'asks'
                    if 'changes' in item:
                         self.books[tid].update(item['changes'])
                    elif 'bids' in item or 'asks' in item:
                         # Snapshot style
                         updates = []
                         if 'bids' in item:
                             for p, s in item['bids']:
                                 updates.append({'side':'BUY', 'price':str(p), 'size':str(s)})
                         if 'asks' in item:
                             for p, s in item['asks']:
                                 updates.append({'side':'SELL', 'price':str(p), 'size':str(s)})
                         self.books[tid].update(updates)
                    
            self.health.update_lag("poly", (now_ts() - ts)*1000)

        except Exception as e:
             self.logger.error(f"Message Handle Error: {e}")

    async def stop(self):
        self.running = False
        if self.ws:
            await self.ws.close()
