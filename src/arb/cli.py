import click
import asyncio
import logging
from .config import Config
from .runtime.orchestrator import Orchestrator
from .ui.live_tui import LiveDashboard

@click.group()
def cli():
    pass

@cli.command()
@click.option('--config', 'config_path', default='config/default.yaml', help='Path to config file')
@click.option('--run-id', default='live_001', help='Run ID for logging')
def paper_live(config_path, run_id):
    """Run the Paper Trading Bot Live."""
    from .runtime.lock import RunLock
    lock = RunLock(run_id)
    if not lock.acquire():
        import sys
        sys.exit(1)

    try:
        import os
        os.makedirs('logs', exist_ok=True)
        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s', filename=f'logs/bot_{run_id}.log')
        
        cfg = Config.load(config_path)
        ui_queue = asyncio.Queue(maxsize=1)
        
        async def main():
            orch = Orchestrator(cfg, run_id, ui_queue)
            tui = LiveDashboard()
            
            tasks = [
                asyncio.create_task(orch.run()),
                asyncio.create_task(tui.run(ui_queue))
            ]
            
            try:
                await asyncio.gather(*tasks)
            except KeyboardInterrupt:
                await orch.shutdown()
            except Exception as e:
                logging.critical(f"Main Crash: {e}", exc_info=True)
                await orch.shutdown()

        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        lock.release()

@cli.command()
@click.option('--config', 'config_path', default='config/default.yaml', help='Path to config file')
def select_market(config_path):
    """Debug: search and select active market."""
    import logging
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    cfg = Config.load(config_path)
    from .health import BotHealth
    health = BotHealth(cfg)
    
    from .polymarket.gamma_client import GammaClient
    from .polymarket.market_selector import MarketSelector
    
    client = GammaClient(cfg.endpoints)
    sel = MarketSelector(cfg, health)
    
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    params = {
        "limit": 100,
        "closed": "false",
        "order": "startDate",
        "ascending": "false",
        "start_date_min": (now - timedelta(minutes=60)).isoformat(),
        "start_date_max": (now + timedelta(minutes=10)).isoformat()
    }
    print(f"Searching /markets with: {params}")
    
    markets = client.search_markets(params)
    print(f"Found {len(markets)} markets.")
    
    selected = sel.select_active_market(markets)

@cli.command()
@click.option('--config', 'config_path', default='config/default.yaml', help='Path to config file')
@click.option('--run-id', default='verify_v1', help='Run ID for logging')
def verify_feeds(config_path, run_id):
    """Verify market discovery and websocket feeds."""
    from .runtime.lock import RunLock
    lock = RunLock(run_id)
    if not lock.acquire():
        import sys
        sys.exit(1)
        
    try:
        import logging
        import sys
        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s', stream=sys.stdout)
        logger = logging.getLogger("verify")
        
        logger.info("VERIFY: Loading Config...")
        cfg = Config.load(config_path)
    
        from .polymarket.gamma_client import GammaClient
        from .polymarket.market_selector import MarketSelector
        from .polymarket.clob_ws import ClobWsClient
        from .polymarket.orderbook import OrderBook
        from .binance.ws_aggtrade import BinanceWsClient
        from .binance.ringbuffer import TradeRingBuffer
        from .health import BotHealth
        from .timeutil import now_ts

        # Check 1: Market Discovery
        logger.info("VERIFY: Checking Market Discovery...")
        client = GammaClient(cfg.endpoints)
        health = BotHealth(cfg)
        sel = MarketSelector(cfg, health)
        
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        params = {
            "limit": 100,
            "closed": "false",
            "order": "startDate",
            "ascending": "false",
            "start_date_min": (now - timedelta(minutes=60)).isoformat(),
            "start_date_max": (now + timedelta(minutes=10)).isoformat()
        }
        
        markets = client.search_markets(params)
        selected = sel.select_active_market(markets)
        
        if not selected:
            logger.error("FAIL: No market found.")
            sys.exit(1)
            
        m = selected['market']
        logger.info(f"PASS: Market Selected - {m.get('question')} (ID: {m.get('id')})")
        
        # Check 2: Poly WS
        logger.info("VERIFY: Checking Polymarket WS...")
        books = {
            selected['token_map']['YES']: OrderBook("YES"),
            selected['token_map']['NO']: OrderBook("NO")
        }
        
        class MockServiceLogger:
            def log_raw_poly(self, data): pass
            
        clob_ws = ClobWsClient(
            cfg.endpoints.poly_ws,
            books,
            health,
            cfg.auth,
            logger,
            service_logger=MockServiceLogger()
        )
        
        async def check_poly():
            task = asyncio.create_task(clob_ws.start())
            start_t = now_ts()
            while (now_ts() - start_t) < 15:
                if health.status.poly_lag_ms > 0 or any(b.get_best()[0] > 0 for b in books.values()):
                    logger.info("PASS: Poly WS Data Flowing.")
                    await clob_ws.stop()
                    await task
                    return True
                await asyncio.sleep(0.5)
            logger.error("FAIL: Poly WS Timeout.")
            await clob_ws.stop()
            try: await task 
            except: pass
            return False

        # Check 3: Binance WS
        logger.info("VERIFY: Checking Binance WS...")
        rb = TradeRingBuffer(1000)
        bin_ws = BinanceWsClient(
            cfg.endpoints.binance_ws,
            cfg.market.binance_symbol,
            rb,
            health,
            logger
        )
        
        async def check_binance():
            task = asyncio.create_task(bin_ws.start())
            start_t = now_ts()
            while (now_ts() - start_t) < 15:
                if health.status.binance_lag_ms > 0:
                    logger.info("PASS: Binance WS Data Flowing.")
                    await bin_ws.stop()
                    await task
                    return True
                await asyncio.sleep(0.5)
            logger.error("FAIL: Binance WS Timeout.")
            await bin_ws.stop()
            await task
            return False
            
        async def main():
            p_res = await check_poly()
            b_res = await check_binance()
            if p_res and b_res:
                logger.info("VERIFICATION PASS")
                return True
            return False

        if not asyncio.run(main()):
            sys.exit(1)

    except KeyboardInterrupt:
        pass
    finally:
        lock.release()

@cli.command()
@click.option('--config', 'config_path', default='config/default.yaml', help='Path to config file')
@click.option('--run-id', default='soak_v1', help='Run ID for logging')
@click.option('--duration-min', default=20, help='Soak duration in minutes')
def verify_soak(config_path, run_id, duration_min):
    """Run verify-feeds repeatedly over a 15-minute boundary."""
    from .runtime.lock import RunLock
    lock = RunLock(run_id)
    if not lock.acquire():
        import sys
        sys.exit(1)

    try:
        import logging
        import sys
        import os
        from .timeutil import now_ts, format_delta_ms
        from .config import Config
        from .runtime.orchestrator import Orchestrator
        
        os.makedirs('logs', exist_ok=True)
        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s', filename=f'logs/soak_{run_id}.log')
        logger = logging.getLogger("soak")
        
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
        logger.addHandler(handler)

        logger.info(f"STARTING SOAK TEST: {run_id} for {duration_min} minutes")
        cfg = Config.load(config_path)
        
        async def main():
            orch = Orchestrator(cfg, run_id)
            start_t = now_ts()
            end_t = start_t + (duration_min * 60)
            orch_task = asyncio.create_task(orch.run())
            
            try:
                while now_ts() < end_t and orch.running:
                    elapsed = now_ts() - start_t
                    rem = end_t - now_ts()
                    logger.info(f"SOAK Progress: {format_delta_ms(elapsed*1000)} / {duration_min}m | Rem: {format_delta_ms(rem*1000)}")
                    await asyncio.sleep(60)
            except KeyboardInterrupt:
                logger.info("Soak Test Interrupted.")
            finally:
                logger.info("Stopping soak session...")
                await orch.shutdown()
                try: 
                    await asyncio.wait_for(orch_task, timeout=5.0)
                except: 
                    pass
                
                stats = orch.broker.get_stats()
                logger.info("==================================================")
                logger.info("SOAK SUMMARY")
                logger.info(f"Total Duration: {format_delta_ms((now_ts() - start_t)*1000)}")
                logger.info(f"Trades Count: {stats.trade_count}")
                logger.info(f"Median Hold: {stats.median_hold_sec:.1f}s")
                logger.info(f"Exit Reasons: {stats.exit_reasons}")
                
                pct_expiry = (stats.exit_reasons.get('EXPIRY', 0) / max(stats.trade_count, 1)) * 100
                logger.info(f"Pct Expiry Exits: {pct_expiry:.1f}%")
                
                pass_all = True
                if pct_expiry >= 5:
                    logger.error("FAIL: Expiry rate >= 5%")
                    pass_all = False
                else:
                    logger.info("PASS: Expiry rate < 5%")
                    
                if stats.trade_count > 0 and stats.exit_reasons.get('EDGE_COLLAPSE', 0) == 0:
                     logger.warning("WARN: No EDGE_COLLAPSE observed despite trades.")
                elif stats.trade_count > 0:
                     logger.info("PASS: EDGE_COLLAPSE observed.")
                
                if pass_all:
                    logger.info("RESULT: SOAK PASS")
                else:
                    logger.error("RESULT: SOAK FAIL")

        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        lock.release()

if __name__ == '__main__':
    cli()
