import os
from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).parent / ".env"

# Alle bekannten Schlüssel mit Standardwerten (für Web-UI und .env-Speicherung)
FIELDS: dict[str, str] = {
    # Solana
    "SOLANA_RPC_URL": "",
    "SOLANA_WS_URL": "",
    "SOLANA_PRIVATE_KEY": "",
    "TARGET_WALLET_SOL": "",
    # Ethereum
    "ETH_RPC_URL": "",
    "ETH_WS_URL": "",
    "ETH_PRIVATE_KEY": "",
    "TARGET_WALLET_ETH": "",
    # KI & Telegram
    "ANTHROPIC_API_KEY": "",
    "TELEGRAM_BOT_TOKEN": "",
    "TELEGRAM_CHAT_ID": "",
    # Scanner / Call-Bot (optional, verbessert Daten)
    "MORALIS_API_KEY": "",
    "BIRDEYE_API_KEY": "",
    # Filter
    "MAX_TRADE_SOL": "1.0",
    "MAX_TRADE_ETH": "0.05",
    "SLIPPAGE_BPS": "50",
    # Scanner-Einstellungen
    "MIN_LIQUIDITY_USD": "5000",
    "MIN_VOLUME_USD": "10000",
    # Flags
    "ENABLE_SOL": "true",
    "ENABLE_ETH": "true",
    "ENABLE_SCANNER": "true",
    "DRY_RUN": "true",
}

SECRET_FIELDS = {
    "SOLANA_PRIVATE_KEY", "ETH_PRIVATE_KEY", "ANTHROPIC_API_KEY",
    "TELEGRAM_BOT_TOKEN", "MORALIS_API_KEY", "BIRDEYE_API_KEY",
}

BOOL_FIELDS = {"ENABLE_SOL", "ENABLE_ETH", "ENABLE_SCANNER", "DRY_RUN"}
FLOAT_FIELDS = {"MAX_TRADE_SOL", "MAX_TRADE_ETH", "MIN_LIQUIDITY_USD", "MIN_VOLUME_USD"}
INT_FIELDS = {"SLIPPAGE_BPS"}


def _as_bool(v: str) -> bool:
    return str(v).lower() in ("1", "true", "yes", "on")


class Config:
    def __init__(self):
        self.reload()

    def reload(self):
        """Liest .env neu ein — wird nach dem Speichern aus dem Web aufgerufen."""
        load_dotenv(ENV_PATH, override=True)
        for key, default in FIELDS.items():
            raw = os.getenv(key, default)
            if key in BOOL_FIELDS:
                setattr(self, key, _as_bool(raw))
            elif key in FLOAT_FIELDS:
                try:
                    setattr(self, key, float(raw))
                except (ValueError, TypeError):
                    setattr(self, key, float(default))
            elif key in INT_FIELDS:
                try:
                    setattr(self, key, int(float(raw)))
                except (ValueError, TypeError):
                    setattr(self, key, int(default))
            else:
                setattr(self, key, raw)

    def as_dict(self, mask_secrets: bool = False) -> dict:
        """Gibt alle Werte zurück (für Web-UI). Secrets können maskiert werden."""
        out = {}
        for key in FIELDS:
            val = getattr(self, key)
            if mask_secrets and key in SECRET_FIELDS and val:
                out[key] = "********"
            else:
                out[key] = val
        return out

    def save(self, data: dict):
        """Speichert Werte in die .env-Datei und lädt neu."""
        current = self._read_env_file()
        for key in FIELDS:
            if key not in data:
                continue
            val = data[key]
            # Maskierte Secrets nicht überschreiben
            if key in SECRET_FIELDS and val == "********":
                continue
            if isinstance(val, bool):
                val = "true" if val else "false"
            current[key] = str(val)
        self._write_env_file(current)
        self.reload()

    def _read_env_file(self) -> dict:
        result = {}
        if ENV_PATH.exists():
            for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                result[k.strip()] = v.strip()
        return result

    def _write_env_file(self, data: dict):
        lines = ["# Auto-generiert vom Web-Terminal — nicht manuell editieren während Bot läuft", ""]
        for key in FIELDS:
            if key in data:
                lines.append(f"{key}={data[key]}")
        ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def is_configured(self) -> bool:
        """Mindestens eine Chain vollständig konfiguriert?"""
        sol_ok = all(getattr(self, k) for k in
                     ("SOLANA_RPC_URL", "SOLANA_PRIVATE_KEY", "TARGET_WALLET_SOL"))
        eth_ok = all(getattr(self, k) for k in
                     ("ETH_RPC_URL", "ETH_PRIVATE_KEY", "TARGET_WALLET_ETH"))
        return sol_ok or eth_ok

    def validate_sol(self):
        missing = [k for k in ("SOLANA_RPC_URL", "SOLANA_WS_URL", "SOLANA_PRIVATE_KEY", "TARGET_WALLET_SOL")
                   if not getattr(self, k)]
        if missing:
            raise EnvironmentError(f"Fehlende Solana-Konfiguration: {missing}")

    def validate_eth(self):
        missing = [k for k in ("ETH_RPC_URL", "ETH_WS_URL", "ETH_PRIVATE_KEY", "TARGET_WALLET_ETH")
                   if not getattr(self, k)]
        if missing:
            raise EnvironmentError(f"Fehlende ETH-Konfiguration: {missing}")


cfg = Config()
