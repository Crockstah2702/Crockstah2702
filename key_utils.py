"""
Schlüssel-Ableitung aus Recovery Phrase (Mnemonic) ODER Private Key.

Solana: reine Python-Implementierung von BIP39 + SLIP-0010 (ed25519),
keine kompilierten Abhängigkeiten. Unterstützt die gängigen Phantom-Pfade.
Phantom-Standard ist m/44'/501'/0'/0'. Wegen unterschiedlicher Wallet-Pfade
IMMER die abgeleitete Adresse mit der echten Wallet vergleichen (Verify im Web).

Ethereum: Standard-MetaMask-Pfad m/44'/60'/0'/0/0 via eth_account.
"""

import hashlib
import hmac
import logging
import unicodedata

from config import cfg

log = logging.getLogger("keys")

HARDENED = 0x80000000

SOLANA_PATHS = {
    "m/44'/501'/0'/0'": "Phantom (Standard)",
    "m/44'/501'/0'": "Solflare / Account-Pfad",
}
DEFAULT_SOL_PATH = "m/44'/501'/0'/0'"


# ─── BIP39: Recovery Phrase → Seed ─────────────────────────────

def mnemonic_to_seed(mnemonic: str, passphrase: str = "") -> bytes:
    mnemonic = unicodedata.normalize("NFKD", mnemonic.strip())
    salt = unicodedata.normalize("NFKD", "mnemonic" + passphrase)
    return hashlib.pbkdf2_hmac("sha512", mnemonic.encode("utf-8"), salt.encode("utf-8"), 2048)


# ─── SLIP-0010 ed25519 (Solana) ───────────────────────────────

def _slip10_master(seed: bytes) -> tuple[bytes, bytes]:
    I = hmac.new(b"ed25519 seed", seed, hashlib.sha512).digest()
    return I[:32], I[32:]  # (key, chaincode)


def _slip10_ckd(key: bytes, chaincode: bytes, index: int) -> tuple[bytes, bytes]:
    # ed25519 erlaubt nur hardened Ableitung
    index |= HARDENED
    data = b"\x00" + key + index.to_bytes(4, "big")
    I = hmac.new(chaincode, data, hashlib.sha512).digest()
    return I[:32], I[32:]


def _derive_ed25519_seed(seed: bytes, path: str) -> bytes:
    key, cc = _slip10_master(seed)
    for part in path.split("/")[1:]:
        idx = int(part.rstrip("'h"))
        key, cc = _slip10_ckd(key, cc, idx)
    return key  # 32-Byte ed25519-Seed


def derive_solana(mnemonic: str, path: str = DEFAULT_SOL_PATH):
    """Leitet ein Solana-Keypair (solders.Keypair) aus der Recovery Phrase ab."""
    from solders.keypair import Keypair
    seed = mnemonic_to_seed(mnemonic)
    seed32 = _derive_ed25519_seed(seed, path)
    return Keypair.from_seed(seed32)


def list_solana_addresses(mnemonic: str) -> list[dict]:
    """Für alle bekannten Pfade die abgeleitete Adresse (zur Prüfung im Web-UI)."""
    out = []
    for path, label in SOLANA_PATHS.items():
        try:
            kp = derive_solana(mnemonic, path)
            out.append({"path": path, "label": label, "address": str(kp.pubkey())})
        except Exception as e:
            log.warning(f"[KEYS] Ableitung {path} fehlgeschlagen: {e}")
    return out


def get_solana_keypair():
    """Solana-Keypair aus Private Key ODER Recovery Phrase (gemäß Config)."""
    from solders.keypair import Keypair
    pk = (cfg.SOLANA_PRIVATE_KEY or "").strip()
    mnemonic = (getattr(cfg, "SOLANA_MNEMONIC", "") or "").strip()
    if pk:
        return Keypair.from_base58_string(pk)
    if mnemonic:
        path = (getattr(cfg, "SOLANA_DERIVATION_PATH", "") or DEFAULT_SOL_PATH).strip()
        return derive_solana(mnemonic, path)
    raise ValueError("Weder SOLANA_PRIVATE_KEY noch SOLANA_MNEMONIC gesetzt")


# ─── Ethereum (eth_account) ────────────────────────────────────

def derive_eth_address(mnemonic: str) -> str:
    from eth_account import Account
    Account.enable_unaudited_hdwallet_features()
    return Account.from_mnemonic(mnemonic.strip()).address


def get_eth_account():
    """ETH-Account aus Private Key ODER Recovery Phrase (gemäß Config)."""
    from eth_account import Account
    Account.enable_unaudited_hdwallet_features()
    pk = (cfg.ETH_PRIVATE_KEY or "").strip()
    mnemonic = (getattr(cfg, "ETH_MNEMONIC", "") or "").strip()
    if pk:
        return Account.from_key(pk)
    if mnemonic:
        return Account.from_mnemonic(mnemonic.strip())
    raise ValueError("Weder ETH_PRIVATE_KEY noch ETH_MNEMONIC gesetzt")
