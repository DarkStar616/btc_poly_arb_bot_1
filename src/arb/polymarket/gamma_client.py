import requests
import logging
from typing import List, Dict, Optional, Any
from ..config import EndpointsConfig

class GammaClient:
    def __init__(self, config: EndpointsConfig):
        self.base_url = config.gamma_api
        self.logger = logging.getLogger("gamma")

    def get_markets(self, query: str, limit: int = 20) -> List[Dict]:
        """Legacy: Fetch events matching query."""
        url = f"{self.base_url}/events"
        params = {
            "limit": limit,
            "q": query,
            "closed": "false" 
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            self.logger.error(f"Gamma Events Error: {e}")
            return []

    def search_markets(self, params: Dict[str, Any]) -> List[Dict]:
        """
        Directly query /markets with custom params.
        """
        url = f"{self.base_url}/markets"
        try:
            # Ensure safe defaults if not provided?
            # User provides strict params.
            self.logger.info(f"Searching markets: {params}")
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            self.logger.error(f"Gamma Markets Error: {e}")
            return []
