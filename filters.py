import logging
from dataclasses import dataclass
from config import cfg

log = logging.getLogger("filters")

SOL_LAMPORTS = 1_000_000_000
ETH_WEI = 10**18

@dataclass
class TradeInfo:
    chain: str          # "SOL" or "ETH"
    input_mint: str     # Token-Adresse rein
    output_mint: str    # Token-Adresse raus
    in_amount: int      # in kleinster Einheit (Lamports / Wei)
    out_amount: int     # geschätzter Output
    dex: str            # z.B. "Jupiter", "Uniswap"
    tx_sig: str         # Original-Transaktion-Signatur
    raw: dict           # vollständige Rohdaten


def apply_max_trade_filter(trade: TradeInfo) -> int:
    """
    Gibt den gefilterten in_amount zurück.
    Wenn der Trade größer als das Limit ist, wird er auf das Limit gekappt.
    """
    if trade.chain == "SOL":
        limit_lamports = int(cfg.MAX_TRADE_SOL * SOL_LAMPORTS)
        if trade.in_amount > limit_lamports:
            log.info(
                f"[SOL] Trade gekappt: {trade.in_amount / SOL_LAMPORTS:.4f} SOL "
                f"→ {cfg.MAX_TRADE_SOL} SOL (Max-Limit)"
            )
            return limit_lamports
        return trade.in_amount

    elif trade.chain == "ETH":
        limit_wei = int(cfg.MAX_TRADE_ETH * ETH_WEI)
        if trade.in_amount > limit_wei:
            log.info(
                f"[ETH] Trade gekappt: {trade.in_amount / ETH_WEI:.6f} ETH "
                f"→ {cfg.MAX_TRADE_ETH} ETH (Max-Limit)"
            )
            return limit_wei
        return trade.in_amount

    return trade.in_amount


def should_copy(trade: TradeInfo) -> bool:
    """Gibt True zurück wenn der Trade kopiert werden soll."""
    if trade.in_amount <= 0:
        log.debug(f"Trade ignoriert: in_amount ist 0")
        return False
    return True
