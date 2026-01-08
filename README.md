# Polymarket Paper Trading Bot (BTC Arb)

A hardened, production-ready paper trading bot for Polymarket BTC 15-minute "Up or Down" markets, featuring Binance-linked price arbitrage and automated market rollover.

## Features
- **Binary Market Selection**: Automated discovery of active BTC-Up/Down outcome tokens.
- **Dual-Feed WebSocket**: High-frequency price updates from Binance and Polymarket CLOB.
- **Hardened CLOB WS**: Dual-mode fallback and silent heartbeat handling for Polymarket's specific WebSocket quirks.
- **Robust Verification**: Built-in CLI commands for feed health (`verify-feeds`) and 20-minute boundary soak tests (`verify-soak`).
- **Windows Optimized**: PowerShell management scripts for process hygiene and single-instance locking.

## Quick Start (Windows)
1. **Install Dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```
2. **Configure Environment**:
   Copy `.env.example` to `.env` and add your Polymarket API credentials (optional for paper trading, but required for CLOB access).
3. **Verify Feeds**:
   ```powershell
   python -m src.arb.cli verify-feeds
   ```
4. **Run Live**:
   ```powershell
   python -m src.arb.cli paper-live
   ```

## Documentation
- [Hardening & Verification Walkthrough](HARDENING_WALKTHROUGH.md)
- [API Specifications](docs/api/README.md)

## Process Management
- `scripts/ps/list_bot.ps1`: List active bot PIDs.
- `scripts/ps/kill_bot.ps1`: Stop all running bot instances.
