import os
from dotenv import load_dotenv

load_dotenv()

def _require(key: str) -> str:
    v = os.getenv(key)
    if not v:
        raise EnvironmentError(f"Fehlende Umgebungsvariable: {key}")
    return v

def _float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default

def _bool(key: str, default: bool) -> bool:
    return os.getenv(key, str(default)).lower() in ("1", "true", "yes")


class Config:
    # Solana
    SOLANA_RPC_URL: str = os.getenv("SOLANA_RPC_URL", "")
    SOLANA_WS_URL: str = os.getenv("SOLANA_WS_URL", "")
    SOLANA_PRIVATE_KEY: str = os.getenv("SOLANA_PRIVATE_KEY", "")
    TARGET_WALLET_SOL: str = os.getenv("TARGET_WALLET_SOL", "")

    # Ethereum
    ETH_RPC_URL: str = os.getenv("ETH_RPC_URL", "")
    ETH_WS_URL: str = os.getenv("ETH_WS_URL", "")
    ETH_PRIVATE_KEY: str = os.getenv("ETH_PRIVATE_KEY", "")
    TARGET_WALLET_ETH: str = os.getenv("TARGET_WALLET_ETH", "")

    # Filter
    MAX_TRADE_SOL: float = _float("MAX_TRADE_SOL", 1.0)
    MAX_TRADE_ETH: float = _float("MAX_TRADE_ETH", 0.05)
    SLIPPAGE_BPS: int = int(_float("SLIPPAGE_BPS", 50))

    # KI & Telegram
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # Flags
    ENABLE_SOL: bool = _bool("ENABLE_SOL", True)
    ENABLE_ETH: bool = _bool("ENABLE_ETH", True)
    DRY_RUN: bool = _bool("DRY_RUN", True)

    def validate_sol(self):
        missing = []
        for k in ("SOLANA_RPC_URL", "SOLANA_WS_URL", "SOLANA_PRIVATE_KEY", "TARGET_WALLET_SOL"):
            if not getattr(self, k):
                missing.append(k)
        if missing:
            raise EnvironmentError(f"Fehlende Solana-Konfiguration: {missing}")

    def validate_eth(self):
        missing = []
        for k in ("ETH_RPC_URL", "ETH_WS_URL", "ETH_PRIVATE_KEY", "TARGET_WALLET_ETH"):
            if not getattr(self, k):
                missing.append(k)
        if missing:
            raise EnvironmentError(f"Fehlende ETH-Konfiguration: {missing}")


cfg = Config()
