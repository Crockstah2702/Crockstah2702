"""
Copy-Trading-Bot Orchestrator.
Startet Monitor und Executor für Solana und/oder Ethereum parallel.
"""

import asyncio
import logging
from config import cfg
from filters import TradeInfo, should_copy

log = logging.getLogger("bot")


class CopyTradingBot:
    def __init__(self):
        self.sol_executor = None
        self.eth_executor = None

    async def _on_sol_trade(self, trade: TradeInfo):
        if not should_copy(trade):
            return
        if self.sol_executor:
            await self.sol_executor.execute(trade)

    async def _on_eth_trade(self, trade: TradeInfo):
        if not should_copy(trade):
            return
        if self.eth_executor:
            await self.eth_executor.execute(trade)

    async def run(self):
        tasks = []

        if cfg.ENABLE_SOL:
            cfg.validate_sol()
            from executor_solana import SolanaExecutor
            from monitor_solana import SolanaMonitor
            self.sol_executor = SolanaExecutor()
            sol_monitor = SolanaMonitor(on_trade=self._on_sol_trade)
            tasks.append(asyncio.create_task(sol_monitor.run(), name="sol_monitor"))
            log.info("[BOT] Solana aktiviert")

        if cfg.ENABLE_ETH:
            cfg.validate_eth()
            from executor_eth import EthExecutor
            from monitor_eth import EthMonitor
            self.eth_executor = EthExecutor()
            eth_monitor = EthMonitor(on_trade=self._on_eth_trade)
            tasks.append(asyncio.create_task(eth_monitor.run(), name="eth_monitor"))
            log.info("[BOT] Ethereum aktiviert")

        if not tasks:
            log.error("Weder Solana noch Ethereum aktiviert. Setze ENABLE_SOL=true oder ENABLE_ETH=true.")
            return

        log.info(f"[BOT] Starte {len(tasks)} Monitor(e)...")
        if cfg.DRY_RUN:
            log.warning("[BOT] *** DRY_RUN=true *** Kein echter Handel — nur Simulation!")

        try:
            await asyncio.gather(*tasks)
        finally:
            if self.sol_executor:
                await self.sol_executor.close()
