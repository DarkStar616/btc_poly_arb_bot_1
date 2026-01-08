import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

@dataclass
class SystemConfig:
    log_dir: str = "logs"
    backtest_mode: str = "paper_live"
    log_level: str = "INFO"

@dataclass
class StrategyConfig:
    initial_capital: float = 10000.0
    risk_fraction: float = 0.02
    max_trade_usd: float = 5000.0
    edge_entry_min: float = 0.071
    edge_exit_min: float = 0.020
    tp_bps: int = 120
    sl_bps: int = 80
    max_hold_sec: int = 180
    max_spread_bps: int = 35
    max_slippage_bps: int = 100
    taker_fee_bps: int = 100

@dataclass
class MarketConfig:
    poly_query: str = "Bitcoin Up or Down"
    duration_min: int = 15
    binance_symbol: str = "btcusdt"

@dataclass
class EndpointsConfig:
    binance_ws: str = "wss://stream.binance.com:9443/ws"
    poly_ws: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    clob_rest: str = "https://clob.polymarket.com"
    gamma_api: str = "https://gamma-api.polymarket.com"

@dataclass
class HealthConfig:
    poly_max_age_ms: int = 5000
    binance_max_age_ms: int = 2000
    book_resync_interval_sec: int = 60
    desync_tolerance_bps: int = 50
    snapshot_drift_bps: int = 100

@dataclass
class AuthConfig:
    api_key: Optional[str] = None
    secret: Optional[str] = None
    passphrase: Optional[str] = None

@dataclass
class Config:
    system: SystemConfig = field(default_factory=SystemConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    market: MarketConfig = field(default_factory=MarketConfig)
    endpoints: EndpointsConfig = field(default_factory=EndpointsConfig)
    health: HealthConfig = field(default_factory=HealthConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)

    @classmethod
    def load(cls, config_path: str = "config/default.yaml") -> 'Config':
        # Load YAML
        with open(config_path, 'r') as f:
            yaml_config = yaml.safe_load(f)

        # Helper to recursively update dataclasses or dicts
        # For simplicity, we manually map for now as structure is flat-ish
        
        def get_env(key, default):
            return os.getenv(key, default)

        # Strategy overrides from ENV
        s_conf = yaml_config.get('strategy', {})
        strategy = StrategyConfig(
            initial_capital=float(get_env('INITIAL_CAPITAL', s_conf.get('initial_capital', 10000))),
            risk_fraction=float(get_env('RISK_FRACTION', s_conf.get('risk_fraction', 0.02))),
            max_trade_usd=float(get_env('MAX_TRADE_USD', s_conf.get('max_trade_usd', 5000))),
            edge_entry_min=float(get_env('EDGE_ENTRY_MIN', s_conf.get('edge_entry_min', 0.071))),
            edge_exit_min=float(get_env('EDGE_EXIT_MIN', s_conf.get('edge_exit_min', 0.020))),
            tp_bps=int(get_env('TP_BPS', s_conf.get('tp_bps', 120))),
            sl_bps=int(get_env('SL_BPS', s_conf.get('sl_bps', 80))),
            max_hold_sec=int(get_env('MAX_HOLD_SEC', s_conf.get('max_hold_sec', 180))),
            max_spread_bps=int(get_env('MAX_SPREAD_BPS', s_conf.get('max_spread_bps', 35))),
            max_slippage_bps=int(get_env('MAX_SLIPPAGE_BPS', s_conf.get('max_slippage_bps', 100))),
            taker_fee_bps=int(get_env('TAKER_FEE_BPS', s_conf.get('taker_fee_bps', 100)))
        )

        sys_conf = yaml_config.get('system', {})
        system = SystemConfig(
            log_dir=get_env('LOG_DIR', sys_conf.get('log_dir', 'logs')),
            backtest_mode=get_env('BACKTEST_MODE', sys_conf.get('backtest_mode', 'paper_live')),
            log_level=sys_conf.get('log_level', 'INFO')
        )

        mk_conf = yaml_config.get('market', {})
        market = MarketConfig(
            poly_query=get_env('POLY_QUERY', mk_conf.get('poly_query', "Bitcoin Up or Down")),
            duration_min=int(get_env('DURATION_MIN', mk_conf.get('duration_min', 15))),
            binance_symbol=get_env('BINANCE_SYMBOL', mk_conf.get('binance_symbol', "btcusdt"))
        )

        ep_conf = yaml_config.get('endpoints', {})
        endpoints = EndpointsConfig(
            binance_ws=get_env('BINANCE_WS_BASE', ep_conf.get('binance_ws', "wss://stream.binance.com:9443/ws")),
            poly_ws=get_env('POLY_WS_BASE', ep_conf.get('poly_ws', "wss://ws-subscriptions-clob.polymarket.com/ws/market")),
            clob_rest=get_env('CLOB_REST_URL', ep_conf.get('clob_rest', "https://clob.polymarket.com")),
            gamma_api=get_env('GAMMA_API_URL', ep_conf.get('gamma_api', "https://gamma-api.polymarket.com"))
        )

        h_conf = yaml_config.get('health', {})
        health = HealthConfig(
            poly_max_age_ms=int(get_env('POLY_MAX_AGE_MS', h_conf.get('poly_max_age_ms', 5000))),
            binance_max_age_ms=int(get_env('BINANCE_MAX_AGE_MS', h_conf.get('binance_max_age_ms', 2000))),
            book_resync_interval_sec=int(get_env('BOOK_RESYNC_INTERVAL_SEC', h_conf.get('book_resync_interval_sec', 60))),
            desync_tolerance_bps=int(get_env('DESYNC_TOLERANCE_BPS', h_conf.get('desync_tolerance_bps', 50))),
            snapshot_drift_bps=int(get_env('SNAPSHOT_DRIFT_BPS', h_conf.get('snapshot_drift_bps', 100)))
        )

        # Auth from ENV only usually, but support yaml placeholder
        auth_conf = yaml_config.get('auth', {})
        
        # Helper to resolve ${VAR} if needed, but simple get_env is enough for now
        api_key = get_env('POLY_API_KEY', None)
        secret = get_env('POLY_SECRET', None)
        phase = get_env('POLY_PASSPHRASE', None)
        
        auth = AuthConfig(api_key=api_key, secret=secret, passphrase=phase)

        return cls(system, strategy, market, endpoints, health, auth)
