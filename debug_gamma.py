import logging
import sys
import json
import requests
from datetime import datetime, timezone, timedelta
from src.arb.config import Config
from src.arb.polymarket.gamma_client import GammaClient

# Setup logging to stderr
logging.basicConfig(level=logging.INFO, stream=sys.stderr, format='%(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger("debug_gamma")

def main():
    try:
        print("DEBUG: Starting debugging script...", file=sys.stderr)
        cfg = Config.load()
        
        # 1. Try /events with 'BTC'
        print("--- PROBING /events q='BTC' ---", file=sys.stderr)
        events_url = f"{cfg.endpoints.gamma_api}/events"
        params_ev = {"limit": 20, "closed": "false", "q": "BTC"}
        try:
            r = requests.get(events_url, params=params_ev, timeout=10)
            r.raise_for_status()
            evs = r.json()
            print(f"  Found {len(evs)} events.", file=sys.stderr)
            for e in evs:
                if "15" in e.get('title', '') or "Up" in e.get('title', ''):
                    print(f"  MATCH EVENT: {e.get('title')} | Slug: {e.get('slug')}", file=sys.stderr)
                    for m in e.get('markets', []):
                         print(f"    Mkt: {m.get('question')}", file=sys.stderr)
        except Exception as e:
            print(f"  Error: {e}", file=sys.stderr)

        # 2. Try /events with 'Bitcoin'
        print("--- PROBING /events q='Bitcoin' ---", file=sys.stderr)
        params_ev['q'] = "Bitcoin"
        try:
            r = requests.get(events_url, params=params_ev, timeout=10)
            r.raise_for_status()
            evs = r.json()
            print(f"  Found {len(evs)} events.", file=sys.stderr)
            for e in evs: 
                 # Print all titles to see
                 print(f"  Event: {e.get('title')}", file=sys.stderr)
        except: pass

        # 3. Try /markets with startDate sort (Newest first)
        print("--- PROBING /markets order=startDate ---", file=sys.stderr)
        params_mk = {
            "limit": 50,
            "closed": "false",
            "order": "startDate",
            "ascending": "false" # Newest first
            # No q, since it breaks things
        }
        endpoint = f"{cfg.endpoints.gamma_api}/markets"
        try:
             r = requests.get(endpoint, params=params_mk, timeout=10)
             r.raise_for_status()
             mkts = r.json()
             print(f"  Found {len(mkts)} markets.", file=sys.stderr)
             
             # Filter for 15m
             found = 0
             for m in mkts:
                  q_text = m.get('question', '')
                  slug = m.get('slug', '')
                  match = "btc-updown-15m" in slug or "Bitcoin Up or Down" in q_text
                  if match:
                       print(f"  MATCH MARKET: {slug} | Exp: {m.get('endDate')}", file=sys.stderr)
                       found += 1
             
             if found == 0:
                  print("  No 15m markets found in top 50 newest.", file=sys.stderr)
                  print("  Sample Newest:", file=sys.stderr)
                  for m in mkts[:3]:
                       print(f"    {m.get('slug')}", file=sys.stderr)
                       
        except Exception as e:
             print(f"Error: {e}", file=sys.stderr)

    except Exception as e:
        logger.exception("Fatal Error in debug script")


if __name__ == "__main__":
    main()
