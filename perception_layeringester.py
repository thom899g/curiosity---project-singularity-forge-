"""
Redundant RPC ingester with failover and cross-verification.
Streams blockchain data from multiple RPC providers to ensure data integrity.
"""
import asyncio
import logging
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime
import json
import time

from web3 import Web3, AsyncWeb3
from web3.types import BlockData, TxData
import websockets
import requests

from config import config
from firebase_setup import firebase_manager

logger = logging.getLogger(__name__)

class RPCHealthMonitor:
    """Monitors RPC health and latency"""
    
    def __init__(self):
        self.response_times: Dict[str, List[float]] = {}
        self.error_counts: Dict[str, int] = {}
        self.last_success: Dict[str, datetime] = {}
    
    async def check_rpc_health(self, rpc_url: str) -> Tuple[bool, float]:
        """
        Check RPC health and measure response time.
        
        Args:
            rpc_url: RPC endpoint URL
            
        Returns:
            Tuple of (is_healthy, response_time_seconds)
        """
        start_time = time.time()
        try:
            if rpc_url.startswith('wss://'):
                # WebSocket health check
                async with websockets.connect(rpc_url, timeout=5) as ws:
                    await ws.send(json.dumps({
                        "jsonrpc": "2.0",
                        "method": "eth_blockNumber",
                        "params": [],
                        "id": 1
                    }))
                    response = await asyncio.wait_for(ws.recv(), timeout=5)
                    result = json.loads(response)
                    if 'result' not in result:
                        raise ValueError("Invalid RPC response")
            else:
                # HTTP health check
                response = requests.post(rpc_url, json={
                    "jsonrpc": "2.0",
                    "method": "eth_blockNumber",
                    "params": [],
                    "id": 1
                }, timeout=5)
                response.raise_for_status()