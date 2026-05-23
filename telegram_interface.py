"""
Telegram-Bot Interface für iPhone-Steuerung.
Sendet Notifications und empfängt Befehle.

Setup:
1. Schreibe @BotFather auf Telegram → /newbot → Token kopieren
2. Starte deinen Bot → schreibe /start → Chat-ID aus den Logs kopieren
3. TELEGRAM_BOT_TOKEN und TELEGRAM_CHAT_ID in .env eintragen
"""

import asyncio
import logging
import time
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode
from config import cfg

log = logging.getLogger("telegram")


class TelegramInterface:
    def __init__(self, position_manager=None, bot_controller=None):
        self.pm = position_manager
        self.controller = bot_controller  # Referenz auf den Bot zum Pausieren etc.
        self._app: Application | None = None
        self._bot: Bot | None = None
        self._paused = False

    async def start(self):
        token = getattr(cfg, "TELEGRAM_BOT_TOKEN", "")
        if not token:
            log.warning("[TG] Kein TELEGRAM_BOT_TOKEN — Telegram deaktiviert.")
            return

        self._app = (
            Application.builder()
            .token(token)
            .build()
        )
        self._bot = self._app.bot

        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("positionen", self._cmd_positionen))
        self._app.add_handler(CommandHandler("pause", self._cmd_pause))
        self._app.add_handler(CommandHandler("resume", self._cmd_resume))
        self._app.add_handler(CommandHandler("hilfe", self._cmd_hilfe))

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        log.info("[TG] Telegram-Bot gestartet ✓")
        await self.send("🤖 *Copy-Trading-Bot gestartet!*\n\nSchreibe /hilfe für alle Befehle.")

    async def stop(self):
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    def is_paused(self) -> bool:
        return self._paused

    # ─── Notifications ────────────────────────────────────────

    async def notify_new_trade(self, symbol: str, chain: str, amount_usd: float,
                                tp_pct: float, sl_pct: float, reasoning: str, tx_sig: str):
        explorer = "solscan.io/tx" if chain == "SOL" else "etherscan.io/tx"
        text = (
            f"📥 *Neuer Trade kopiert!*\n\n"
            f"Token: `{symbol}` ({chain})\n"
            f"Investiert: `${amount_usd:.2f}`\n"
            f"✅ TP: `+{tp_pct:.0f}%`\n"
            f"🛑 SL: `-{sl_pct:.0f}%`\n"
            f"🧠 KI: _{reasoning}_\n\n"
            f"[TX ansehen](https://{explorer}/{tx_sig})"
        )
        await self.send(text)

    async def notify_close(self, symbol: str, chain: str, reason: str,
                            pnl_pct: float, pnl_usd: float):
        if reason == "TP":
            emoji = "🟢"
            title = "Take Profit ausgelöst!"
        else:
            emoji = "🔴"
            title = "Stop Loss ausgelöst!"

        text = (
            f"{emoji} *{title}*\n\n"
            f"Token: `{symbol}` ({chain})\n"
            f"P&L: `{pnl_pct:+.1f}%` (`${pnl_usd:+.2f}`)"
        )
        await self.send(text)

    async def notify_error(self, message: str):
        await self.send(f"⚠️ *Fehler:* {message}")

    async def send(self, text: str):
        chat_id = getattr(cfg, "TELEGRAM_CHAT_ID", "")
        if not chat_id or not self._bot:
            return
        try:
            await self._bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
            )
        except Exception as e:
            log.error(f"[TG] Senden fehlgeschlagen: {e}")

    # ─── Commands ─────────────────────────────────────────────

    async def _cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        log.info(f"[TG] /start von Chat-ID: {chat_id}")
        await update.message.reply_text(
            f"✅ Bot verbunden!\n\nDeine Chat-ID: `{chat_id}`\n\nSchreibe /hilfe für Befehle.",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def _cmd_hilfe(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        text = (
            "🤖 *Copy-Trading-Bot Befehle*\n\n"
            "/status — Bot-Status & Zusammenfassung\n"
            "/positionen — Alle offenen Positionen\n"
            "/pause — Trading pausieren\n"
            "/resume — Trading fortsetzen\n"
            "/hilfe — Diese Hilfe"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        status = "⏸ PAUSIERT" if self._paused else "▶️ AKTIV"
        dry = " | 🔧 DRY RUN" if cfg.DRY_RUN else ""
        positionen = 0
        if self.pm:
            positionen = len(await self.pm.get_all())

        text = (
            f"📊 *Bot-Status*\n\n"
            f"Status: {status}{dry}\n"
            f"Offene Positionen: `{positionen}`\n"
            f"SOL-Ziel: `{cfg.TARGET_WALLET_SOL[:12]}…`\n"
            f"ETH-Ziel: `{cfg.TARGET_WALLET_ETH[:12]}…`\n"
            f"Max SOL/Trade: `{cfg.MAX_TRADE_SOL} SOL`\n"
            f"Max ETH/Trade: `{cfg.MAX_TRADE_ETH} ETH`"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_positionen(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self.pm:
            await update.message.reply_text("Keine Position-Daten verfügbar.")
            return

        positions = await self.pm.get_all()
        if not positions:
            await update.message.reply_text("📭 Keine offenen Positionen.")
            return

        lines = ["📋 *Offene Positionen:*\n"]
        for p in positions:
            from price_fetcher import get_token_price
            current = await get_token_price(p.chain, p.output_mint)
            pnl_str = f"{p.pnl_pct(current):+.1f}%" if current else "?"
            lines.append(
                f"• `{p.symbol}` ({p.chain}) | P&L: `{pnl_str}`\n"
                f"  TP: +{p.tp_pct:.0f}% | SL: -{p.sl_pct:.0f}%"
            )

        await update.message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN
        )

    async def _cmd_pause(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        self._paused = True
        await update.message.reply_text("⏸ *Trading pausiert.* Neue Trades werden ignoriert.", parse_mode=ParseMode.MARKDOWN)

    async def _cmd_resume(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        self._paused = False
        await update.message.reply_text("▶️ *Trading fortgesetzt!*", parse_mode=ParseMode.MARKDOWN)
