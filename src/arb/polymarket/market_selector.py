import logging
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional
from ..health import Gate

class MarketSelector:
    def __init__(self, config, health_mgr=None):
        self.config = config
        self.health = health_mgr
        self.logger = logging.getLogger("selector")

    def select_active_market(self, markets: List[Dict]) -> Optional[Dict]:
        """
        Filter markets list using robust client-side logic.
        """
        now = datetime.now(timezone.utc)
        candidates = []
        
        # Diagnostics buffer
        skipped_reasons = {}

        for m in markets:
            mid = m.get('id', 'unknown')
            try:
                # 1. Filter by Slug or Question
                q_text = m.get('question', '') or ''
                slug = m.get('slug', '') or ''
                
                # Check match (Case insensitive)
                match = "btc-updown-15m" in slug.lower() or "bitcoin up or down" in q_text.lower()
                if not match:
                    skipped_reasons['no_match'] = skipped_reasons.get('no_match', 0) + 1
                    continue

                # 2. Check Active
                if not m.get('active'):
                     skipped_reasons['inactive'] = skipped_reasons.get('inactive', 0) + 1
                     continue
                     
                # 3. Check Date Window
                end_iso = m.get('endDate')
                start_iso = m.get('startDate')
                if not end_iso or not start_iso: 
                    skipped_reasons['no_dates'] = skipped_reasons.get('no_dates', 0) + 1
                    continue
                    
                # Robust Parse
                try:
                    end_dt = datetime.fromisoformat(end_iso.replace('Z', '+00:00'))
                    start_dt = datetime.fromisoformat(start_iso.replace('Z', '+00:00'))
                except ValueError:
                    skipped_reasons['bad_dates'] = skipped_reasons.get('bad_dates', 0) + 1
                    continue
                
                # Logic: startDate <= now < endDate
                # Allow a small buffer? Prompt says "startDate <= now < endDate"
                if not (start_dt <= now < end_dt):
                    skipped_reasons['out_of_window'] = skipped_reasons.get('out_of_window', 0) + 1
                    # self.logger.debug(f"Skipping {mid}: Window mismatch. Now {now}, Start {start_dt}, End {end_dt}")
                    continue

                # 4. Check Outcomes & Tokens
                token_map = self._map_tokens_robust(m)
                
                if not token_map:
                    # Gating/Diagnostic
                    self.logger.warning(f"Market {mid} AMBIGUOUS: Map failed. Q: {q_text} Outcomes: {m.get('outcomes')} Clob: {m.get('clobTokenIds')}")
                    skipped_reasons['ambiguous'] = skipped_reasons.get('ambiguous', 0) + 1
                    continue

                candidates.append({
                    'market': m,
                    'token_map': token_map,
                    'end_dt': end_dt,
                    'start_dt': start_dt,
                    'end_iso': end_iso
                })
                
            except Exception as e:
                self.logger.error(f"Error parsing market {mid}: {e}")
                continue

        # Sort by nearest expiry? Or Start Date?
        # Prompt says "Active BTC 15-min... selected reliably"
        # Usually checking nearest expiry that is > now
        candidates.sort(key=lambda x: x['end_dt'])
        
        if candidates:
            best = candidates[0]
            if self.health:
                 self.health.clear_gate(Gate.MARKET_AMBIGUOUS)
            return best
            
        # If failure, log summary + verbose diagnostics
        self.logger.info(f"Selection Failed. Scanned {len(markets)}. Reasons: {skipped_reasons}")
        
        # Verbose dump of top candidates for debugging
        if markets:
            self.logger.info("Top 5 Candidate Markets (Verbose Dump):")
            for m in markets[:5]:
                self.logger.info(
                    f"  ID: {m.get('id')} | Slug: {m.get('slug')} | Q: {m.get('question')}\n"
                    f"    Active: {m.get('active')} | Start: {m.get('startDate')} | End: {m.get('endDate')}\n"
                    f"    Outcomes: {m.get('outcomes')} | Tokens: {m.get('clobTokenIds')}"
                )
        return None

    def _map_tokens_robust(self, market: Dict) -> Optional[Dict[str, str]]:
        outcomes = market.get('outcomes')
        clob_ids = market.get('clobTokenIds')
        
        # Parse JSON strings if necessary
        if isinstance(outcomes, str):
            try: outcomes = json.loads(outcomes)
            except: pass
        if isinstance(clob_ids, str):
            try: clob_ids = json.loads(clob_ids)
            except: pass
        
        if not outcomes or not clob_ids:
            return None
            
        if len(outcomes) != len(clob_ids):
            return None
            
        # Normalize
        out_norm = [str(o).lower().strip() for o in outcomes]
        
        mapping = {}
        
        # Robust Mapping Strategy
        # 1. Exact Up/Down
        if "up" in out_norm and "down" in out_norm:
            mapping['YES'] = clob_ids[out_norm.index("up")]
            mapping['NO'] = clob_ids[out_norm.index("down")]
            return mapping
            
        # 2. Yes/No
        if "yes" in out_norm and "no" in out_norm:
            mapping['YES'] = clob_ids[out_norm.index("yes")]
            mapping['NO'] = clob_ids[out_norm.index("no")]
            return mapping

        return None
