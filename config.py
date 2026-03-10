"""
Configuration management for Project Chronos Forge.
Centralizes all environment variables with type safety and validation.
"""
import os
import json
from dataclasses import dataclass
from typing import List, Optional
from decimal import Decimal
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class RPCConfig:
    """RPC endpoint configuration with redundancy"""
    primary: str
    secondary: List[str]
    flashbots: str
    
    def get_fallback_rpc(self, attempt: int) -> str:
        """Get RPC URL based on retry attempt with fallback logic"""
        rpcs = [self.primary] + self.secondary
        return rpcs[min(attempt, len(rpcs) - 1)]

@dataclass
class WalletConfig:
    """Secure wallet configuration with validation"""
    address: str
    private_key_env_var: str
    check_balance_threshold: Decimal = Decimal('0.001')  # Minimum ETH balance
    
    def get_private_key(self) -> Optional[str]:
        """Safely retrieve private key from environment"""
        try:
            # For production: implement decryption here
            return os.environ.get(self.private_key_env_var)
        except Exception as e:
            logger.error(f"Failed to retrieve private key: {e}")
            return None
    
    def validate_address(self) -> bool:
        """Validate Ethereum address format"""
        if not self.address:
            return False
        return (self.address.startswith('0x') and 
                len(self.address) == 42 and 
                all(c in '0123456789abcdefABCDEF' for c in self.address[2:]))

@dataclass
class TradingConfig:
    """Risk-managed trading parameters"""
    target_daily_gain: Decimal
    max_daily_loss: Decimal
    initial_capital: Decimal
    max_position_size: Decimal  # As percentage of capital
    min_profit_threshold: Decimal = Decimal('0.002')  # 0.2% minimum profit
    max_slippage_bps: int = 50  # 0.5% max slippage
    
    def validate(self) -> bool:
        """Validate trading parameters are safe"""
        conditions = [
            self.target_daily_gain <= Decimal('0.1'),  # Max 10% daily
            self.max_daily_loss <= Decimal('0.05'),   # Max 5% daily loss
            self.max_position_size <= Decimal('0.7'), # Max 70% position
            self.min_profit_threshold > Decimal('0')
        ]
        return all(conditions)

@dataclass
class FirebaseConfig:
    """Firebase configuration with credential validation"""
    credentials_path: Path
    project_id: str
    
    def validate_credentials(self) -> bool:
        """Verify Firebase credentials file exists and is valid JSON"""
        try:
            if not self.credentials_path.exists():
                logger.error(f"Firebase credentials not found at {self.credentials_path}")
                return False
            
            with open(self.credentials_path) as f:
                json.load(f)  # Validate JSON
            
            return True
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Invalid Firebase credentials: {e}")
            return False

class ChronosConfig:
    """Main configuration singleton"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize configuration from environment variables"""
        self.rpc = RPCConfig(
            primary=os.getenv('BASE_RPC_1', 'https://mainnet.base.org'),
            secondary=[
                os.getenv('BASE_RPC_2', ''),
                os.getenv('BASE_RPC_3', '')
            ],
            flashbots=os.getenv('FLASHBOTS_RPC', 'https://rpc.flashbots.net')
        )
        
        self.wallet = WalletConfig(
            address=os.getenv('HOT_WALLET_ADDRESS', ''),
            private_key_env_var='HOT_WALLET_PK'
        )
        
        self.trading = TradingConfig(
            target_daily_gain=Decimal(os.getenv('TARGET_DAILY_GAIN', '0.05')),
            max_daily_loss=Decimal(os.getenv('MAX_DAILY_LOSS', '0.03')),
            initial_capital=Decimal(os.getenv('INITIAL_CAPITAL', '1000')),
            max_position_size=Decimal(os.getenv('MAX_POSITION_SIZE', '0.5'))
        )
        
        self.firebase = FirebaseConfig(
            credentials_path=Path(os.getenv('FIREBASE_CREDENTIALS_PATH', './serviceAccountKey.json')),
            project_id=os.getenv('FIREBASE_PROJECT_ID', '')
        )
        
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
        
        # Validate critical configurations
        self._validate_config()
    
    def _validate_config(self):
        """Validate all configurations and log warnings"""
        if not self.wallet.validate_address():
            logger.warning("Wallet address format validation failed")
        
        if not self.trading.validate():
            logger.warning("Trading parameters exceed safe thresholds")
        
        if not self.firebase.validate_credentials():
            logger.error("Firebase credentials validation failed")
        
        if not self.telegram_token or not self.telegram_chat_id:
            logger.warning("Telegram alerts disabled - no bot token/chat_id")
    
    def get_safe_rpc_list(self) -> List[str]:
        """Get list of non-empty RPC endpoints"""
        all_rpcs = [self.rpc.primary] + self.rpc.secondary + [self.rpc.flashbots]
        return [rpc for rpc in all_rpcs if rpc and 'YOUR_KEY' not in rpc]

# Global configuration instance
config = ChronosConfig()