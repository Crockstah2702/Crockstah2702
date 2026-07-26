#!/usr/bin/env python3
"""
Solana Wallet Token Scanner
===========================

Überwacht eine Solana-Wallet und erkennt, wenn neue Tokens gekauft (oder
verkauft) werden. Für jede Position wird der Gewinn/Verlust (P&L) berechnet
und bei neuen Käufen eine Benachrichtigung ausgegeben (Konsole + optional
Telegram).

Funktionsweise (kurz):
- Per Solana-RPC werden alle SPL-Token-Konten der Wallet abgefragt
  (Token- und Token-2022-Programm).
- Die Bestände werden zwischen den Durchläufen verglichen:
    * neuer Token / gestiegener Bestand  -> Kauf  (Buy)
    * gesunkener Bestand                 -> Verkauf (Sell, realisiert P&L)
- Preise kommen von der öffentlichen DexScreener-API (kein API-Key nötig).
- Der Einstiegspreis wird beim Erkennen eines Kaufs als Kostenbasis
  gespeichert (gewichteter Durchschnitt). Daraus ergibt sich der
  unrealisierte P&L = Menge * (aktueller Preis - Ø Einstandspreis).

Hinweis zur Genauigkeit: Als Kaufpreis wird der Marktpreis zum Zeitpunkt
der Erkennung verwendet (Näherung). Für ein Monitoring-Tool ist das i.d.R.
ausreichend; auf die Sekunde exakte Ausführungspreise erfordern das
Parsen jeder einzelnen Swap-Transaktion.

Benutzung:
    python scanner.py <WALLET_ADRESSE>
    python scanner.py <WALLET_ADRESSE> --interval 30
    python scanner.py <WALLET_ADRESSE> --once        # einmaliger Scan (für cron)

Telegram-Benachrichtigungen (optional) über Umgebungsvariablen:
    export TELEGRAM_BOT_TOKEN="123456:ABC..."
    export TELEGRAM_CHAT_ID="987654321"

Eigener RPC-Endpunkt (empfohlen, öffentlicher ist rate-limitiert):
    export SOLANA_RPC_URL="https://dein-rpc-endpunkt"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit("Fehlt: 'requests'. Bitte installieren mit:  pip install requests")


# --------------------------------------------------------------------------- #
# Konstanten
# --------------------------------------------------------------------------- #

DEFAULT_RPC_URL = os.environ.get(
    "SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"
)

# SPL-Token-Programme (klassisch + Token-2022)
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

# Wrapped SOL – wird bei der Kaufanalyse ignoriert (nur "Cash", kein Token-Kauf)
WSOL_MINT = "So11111111111111111111111111111111111111112"

DEXSCREENER_TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens/"

DEFAULT_STATE_FILE = os.path.join(os.path.dirname(__file__), "wallet_state.json")

# ANSI-Farben für die Konsole
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


# --------------------------------------------------------------------------- #
# Datenmodell
# --------------------------------------------------------------------------- #

@dataclass
class Position:
    """Eine gehaltene Token-Position samt Kostenbasis für P&L."""
    mint: str
    symbol: str = "?"
    amount: float = 0.0            # aktueller Bestand (UI-Menge)
    avg_cost_usd: float = 0.0      # Ø Einstandspreis pro Token (USD)
    realized_pnl_usd: float = 0.0  # bereits realisierter Gewinn/Verlust
    first_seen: str = ""           # ISO-Zeitstempel
    last_price_usd: float = 0.0

    def cost_basis(self) -> float:
        return self.amount * self.avg_cost_usd

    def market_value(self, price: float) -> float:
        return self.amount * price

    def unrealized_pnl(self, price: float) -> float:
        return self.amount * (price - self.avg_cost_usd)


# --------------------------------------------------------------------------- #
# Solana-RPC
# --------------------------------------------------------------------------- #

class SolanaRPC:
    def __init__(self, url: str, timeout: int = 20):
        self.url = url
        self.timeout = timeout
        self.session = requests.Session()
        self._id = 0

    def _call(self, method: str, params: List[Any]) -> Any:
        self._id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._id,
            "method": method,
            "params": params,
        }
        resp = self.session.post(self.url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"RPC-Fehler ({method}): {data['error']}")
        return data.get("result")

    def get_token_accounts(self, owner: str) -> Dict[str, Tuple[float, int]]:
        """Liefert {mint: (ui_amount, decimals)} über beide Token-Programme."""
        holdings: Dict[str, Tuple[float, int]] = {}
        for program_id in (TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID):
            result = self._call(
                "getTokenAccountsByOwner",
                [
                    owner,
                    {"programId": program_id},
                    {"encoding": "jsonParsed"},
                ],
            )
            for acc in (result or {}).get("value", []):
                info = acc["account"]["data"]["parsed"]["info"]
                mint = info["mint"]
                token_amount = info["tokenAmount"]
                ui_amount = token_amount.get("uiAmount") or 0.0
                decimals = token_amount.get("decimals", 0)
                if ui_amount <= 0:
                    continue
                # Mehrere Konten desselben Mints zusammenzählen
                prev = holdings.get(mint, (0.0, decimals))
                holdings[mint] = (prev[0] + ui_amount, decimals)
        return holdings

    def get_sol_balance(self, owner: str) -> float:
        result = self._call("getBalance", [owner])
        lamports = (result or {}).get("value", 0)
        return lamports / 1_000_000_000


# --------------------------------------------------------------------------- #
# Preise (DexScreener)
# --------------------------------------------------------------------------- #

class PriceProvider:
    """Holt USD-Preise und Symbole per DexScreener (mit kurzem Cache)."""

    def __init__(self, ttl: int = 20):
        self.ttl = ttl
        self.session = requests.Session()
        self._cache: Dict[str, Tuple[float, Tuple[float, str]]] = {}

    def get(self, mint: str) -> Tuple[float, str]:
        """Gibt (preis_usd, symbol) zurück. Preis 0.0 wenn unbekannt."""
        now = time.time()
        cached = self._cache.get(mint)
        if cached and now - cached[0] < self.ttl:
            return cached[1]

        price, symbol = 0.0, mint[:4] + "…"
        try:
            resp = self.session.get(DEXSCREENER_TOKEN_URL + mint, timeout=15)
            resp.raise_for_status()
            pairs = (resp.json() or {}).get("pairs") or []
            # Paar mit höchster Liquidität wählen (robuster Preis)
            best = None
            best_liq = -1.0
            for p in pairs:
                liq = ((p.get("liquidity") or {}).get("usd")) or 0.0
                if liq > best_liq:
                    best_liq, best = liq, p
            if best:
                price = float(best.get("priceUsd") or 0.0)
                base = best.get("baseToken") or {}
                quote = best.get("quoteToken") or {}
                if base.get("address") == mint:
                    symbol = base.get("symbol") or symbol
                elif quote.get("address") == mint:
                    symbol = quote.get("symbol") or symbol
                else:
                    symbol = base.get("symbol") or symbol
        except Exception:
            # Netzfehler/Unbekannter Token -> Preis bleibt 0, Symbol Näherung
            pass

        self._cache[mint] = (now, (price, symbol))
        return price, symbol


# --------------------------------------------------------------------------- #
# Benachrichtigungen
# --------------------------------------------------------------------------- #

class Notifier:
    """Verteilt Meldungen an Konsole, Telegram und WhatsApp.

    WhatsApp unterstützt drei Anbieter (per Env WHATSAPP_PROVIDER oder
    automatische Erkennung anhand der gesetzten Variablen):

    - "callmebot" : kostenlos, kein Account, nur an die eigene Nummer.
                    Env: CALLMEBOT_APIKEY, WHATSAPP_TO
    - "twilio"    : dedizierte Bot-Nummer über Twilio (Sandbox oder eigen).
                    Env: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
                         TWILIO_WHATSAPP_FROM, WHATSAPP_TO
    - "cloud"     : offizielle WhatsApp Business Cloud API (Meta).
                    Env: WHATSAPP_CLOUD_TOKEN, WHATSAPP_PHONE_NUMBER_ID,
                         WHATSAPP_TO
    """

    def __init__(self):
        self._session = requests.Session()

        # --- Telegram ---
        self.tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        self.tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        self.telegram_enabled = bool(self.tg_token and self.tg_chat)

        # --- WhatsApp ---
        self.wa_to = os.environ.get("WHATSAPP_TO", "").strip()
        self.callmebot_key = os.environ.get("CALLMEBOT_APIKEY", "").strip()
        self.twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
        self.twilio_token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
        self.twilio_from = os.environ.get("TWILIO_WHATSAPP_FROM", "").strip()
        self.cloud_token = os.environ.get("WHATSAPP_CLOUD_TOKEN", "").strip()
        self.cloud_phone_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "").strip()

        self.wa_provider = self._detect_wa_provider(
            os.environ.get("WHATSAPP_PROVIDER", "").strip().lower()
        )
        self.whatsapp_enabled = self.wa_provider is not None

    def _detect_wa_provider(self, forced: str) -> Optional[str]:
        """Wählt den WhatsApp-Anbieter; validiert die nötigen Variablen."""
        def ok(provider: str) -> bool:
            if provider == "callmebot":
                return bool(self.callmebot_key and self.wa_to)
            if provider == "twilio":
                return bool(self.twilio_sid and self.twilio_token
                            and self.twilio_from and self.wa_to)
            if provider == "cloud":
                return bool(self.cloud_token and self.cloud_phone_id and self.wa_to)
            return False

        if forced:
            if ok(forced):
                return forced
            print(f"{YELLOW}[Warnung] WHATSAPP_PROVIDER='{forced}', aber es "
                  f"fehlen Variablen – WhatsApp ist deaktiviert.{RESET}")
            return None
        # Auto-Erkennung in sinnvoller Reihenfolge
        for provider in ("twilio", "cloud", "callmebot"):
            if ok(provider):
                return provider
        return None

    # ---------------------------------------------------------------- #
    def send(self, message_console: str, message_plain: str) -> None:
        print(message_console)
        if self.telegram_enabled:
            self._send_telegram(message_plain)
        if self.whatsapp_enabled:
            self._send_whatsapp(message_plain)

    def _send_telegram(self, text: str) -> None:
        try:
            url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
            self._session.post(
                url,
                json={
                    "chat_id": self.tg_chat,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=15,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"{YELLOW}[Warnung] Telegram-Versand fehlgeschlagen: {exc}{RESET}")

    def _send_whatsapp(self, text: str) -> None:
        try:
            if self.wa_provider == "callmebot":
                self._wa_callmebot(text)
            elif self.wa_provider == "twilio":
                self._wa_twilio(text)
            elif self.wa_provider == "cloud":
                self._wa_cloud(text)
        except Exception as exc:  # noqa: BLE001
            print(f"{YELLOW}[Warnung] WhatsApp-Versand fehlgeschlagen: {exc}{RESET}")

    def _wa_callmebot(self, text: str) -> None:
        # https://www.callmebot.com/blog/free-api-whatsapp-messages/
        resp = self._session.get(
            "https://api.callmebot.com/whatsapp.php",
            params={"phone": self.wa_to, "text": text, "apikey": self.callmebot_key},
            timeout=20,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"CallMeBot HTTP {resp.status_code}: {resp.text[:200]}")

    def _wa_twilio(self, text: str) -> None:
        # https://www.twilio.com/docs/whatsapp
        from_ = self.twilio_from
        to_ = self.wa_to
        if not from_.startswith("whatsapp:"):
            from_ = "whatsapp:" + from_
        if not to_.startswith("whatsapp:"):
            to_ = "whatsapp:" + to_
        url = (f"https://api.twilio.com/2010-04-01/Accounts/"
               f"{self.twilio_sid}/Messages.json")
        resp = self._session.post(
            url,
            data={"From": from_, "To": to_, "Body": text},
            auth=(self.twilio_sid, self.twilio_token),
            timeout=20,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Twilio HTTP {resp.status_code}: {resp.text[:300]}")

    def _wa_cloud(self, text: str) -> None:
        # https://developers.facebook.com/docs/whatsapp/cloud-api
        to_ = self.wa_to.lstrip("+").replace("whatsapp:", "").replace("+", "")
        url = f"https://graph.facebook.com/v20.0/{self.cloud_phone_id}/messages"
        resp = self._session.post(
            url,
            headers={"Authorization": f"Bearer {self.cloud_token}"},
            json={
                "messaging_product": "whatsapp",
                "to": to_,
                "type": "text",
                "text": {"body": text},
            },
            timeout=20,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Cloud API HTTP {resp.status_code}: {resp.text[:300]}")


# --------------------------------------------------------------------------- #
# State-Persistenz
# --------------------------------------------------------------------------- #

def load_state(path: str) -> Dict[str, Position]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return {mint: Position(**data) for mint, data in raw.items()}
    except Exception as exc:  # noqa: BLE001
        print(f"{YELLOW}[Warnung] State konnte nicht geladen werden: {exc}{RESET}")
        return {}


def save_state(path: str, positions: Dict[str, Position]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({m: asdict(p) for m, p in positions.items()}, fh, indent=2)
    os.replace(tmp, path)


# --------------------------------------------------------------------------- #
# Formatierung
# --------------------------------------------------------------------------- #

def fmt_usd(value: float) -> str:
    if abs(value) >= 1:
        return f"${value:,.2f}"
    if value == 0:
        return "$0.00"
    return f"${value:.6f}".rstrip("0").rstrip(".")


def fmt_amount(value: float) -> str:
    if value >= 1000:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:,.4f}"
    return f"{value:.6f}".rstrip("0").rstrip(".")


def pnl_color(value: float) -> str:
    if value > 0:
        return GREEN
    if value < 0:
        return RED
    return RESET


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


# --------------------------------------------------------------------------- #
# Scanner-Kern
# --------------------------------------------------------------------------- #

class WalletScanner:
    def __init__(
        self,
        wallet: str,
        rpc: SolanaRPC,
        prices: PriceProvider,
        notifier: Notifier,
        state_file: str,
        min_value_usd: float = 1.0,
    ):
        self.wallet = wallet
        self.rpc = rpc
        self.prices = prices
        self.notifier = notifier
        self.state_file = state_file
        self.min_value_usd = min_value_usd
        self.positions: Dict[str, Position] = load_state(state_file)
        self.first_run = len(self.positions) == 0

    # -- eine Iteration ---------------------------------------------------- #
    def scan_once(self) -> None:
        holdings = self.rpc.get_token_accounts(self.wallet)
        events: List[str] = []

        # 1) Käufe / Verkäufe erkennen
        for mint, (amount, _decimals) in holdings.items():
            if mint == WSOL_MINT:
                continue
            price, symbol = self.prices.get(mint)
            pos = self.positions.get(mint)

            if pos is None:
                # Neuer Token
                if amount * price < self.min_value_usd and price > 0:
                    continue  # Staub/Airdrop ignorieren
                pos = Position(
                    mint=mint,
                    symbol=symbol,
                    amount=amount,
                    avg_cost_usd=price,
                    first_seen=now_iso(),
                    last_price_usd=price,
                )
                self.positions[mint] = pos
                if not self.first_run:
                    events.append(self._buy_event(pos, amount, price, is_new=True))
            else:
                pos.symbol = symbol or pos.symbol
                pos.last_price_usd = price
                delta = amount - pos.amount
                if delta > 1e-9:  # Zukauf
                    total_cost = pos.cost_basis() + delta * price
                    pos.amount = amount
                    pos.avg_cost_usd = total_cost / amount if amount else 0.0
                    if not self.first_run:
                        events.append(self._buy_event(pos, delta, price, is_new=False))
                elif delta < -1e-9:  # Verkauf
                    sold = -delta
                    pos.realized_pnl_usd += sold * (price - pos.avg_cost_usd)
                    pos.amount = amount
                    if not self.first_run:
                        events.append(self._sell_event(pos, sold, price))

        # 2) Positionen erkennen, die komplett verkauft/verschwunden sind
        for mint, pos in list(self.positions.items()):
            if mint not in holdings and pos.amount > 0:
                price, _ = self.prices.get(mint)
                pos.realized_pnl_usd += pos.amount * (price - pos.avg_cost_usd)
                if not self.first_run:
                    events.append(self._sell_event(pos, pos.amount, price))
                pos.amount = 0.0

        save_state(self.state_file, self.positions)

        if self.first_run:
            print(
                f"{DIM}Erster Lauf: {len(self.positions)} Position(en) als "
                f"Ausgangsbestand erfasst. Ab jetzt werden neue Käufe gemeldet.{RESET}"
            )
            self.first_run = False

        for ev in events:
            self.notifier.send(ev, self._strip_ansi(ev))

        self._print_portfolio()

    # -- Event-Nachrichten ------------------------------------------------- #
    def _buy_event(self, pos: Position, amount: float, price: float, is_new: bool) -> str:
        label = "🟢 NEUER TOKEN GEKAUFT" if is_new else "🟢 ZUKAUF"
        value = amount * price
        return (
            f"\n{BOLD}{GREEN}{label}{RESET}\n"
            f"  Token:   {BOLD}{pos.symbol}{RESET}  ({pos.mint})\n"
            f"  Menge:   {fmt_amount(amount)}\n"
            f"  Preis:   {fmt_usd(price)}\n"
            f"  Wert:    {fmt_usd(value)}\n"
            f"  Ø Einstand: {fmt_usd(pos.avg_cost_usd)}\n"
            f"  Zeit:    {now_iso()}"
        )

    def _sell_event(self, pos: Position, amount: float, price: float) -> str:
        realized = amount * (price - pos.avg_cost_usd)
        col = pnl_color(realized)
        return (
            f"\n{BOLD}{RED}🔴 VERKAUF{RESET}\n"
            f"  Token:   {BOLD}{pos.symbol}{RESET}  ({pos.mint})\n"
            f"  Menge:   {fmt_amount(amount)}\n"
            f"  Preis:   {fmt_usd(price)}\n"
            f"  Realisierter P&L: {col}{fmt_usd(realized)}{RESET}\n"
            f"  Zeit:    {now_iso()}"
        )

    # -- Portfolio-Übersicht ---------------------------------------------- #
    def _print_portfolio(self) -> None:
        active = {m: p for m, p in self.positions.items() if p.amount > 0}
        if not active:
            print(f"{DIM}Keine aktiven Positionen.{RESET}")
            return

        print(f"\n{BOLD}{CYAN}── Portfolio ({now_iso()}) ─────────────────────────{RESET}")
        header = (
            f"{'Token':<12}{'Menge':>16}{'Preis':>14}"
            f"{'Wert':>14}{'Ø Einstand':>14}{'P&L (unreal.)':>18}"
        )
        print(BOLD + header + RESET)

        total_value = 0.0
        total_unreal = 0.0
        total_realized = 0.0
        for pos in sorted(active.values(), key=lambda p: -p.market_value(p.last_price_usd)):
            price = pos.last_price_usd
            value = pos.market_value(price)
            unreal = pos.unrealized_pnl(price)
            total_value += value
            total_unreal += unreal
            total_realized += pos.realized_pnl_usd
            col = pnl_color(unreal)
            pct = ""
            if pos.avg_cost_usd > 0:
                pct = f" ({(price / pos.avg_cost_usd - 1) * 100:+.1f}%)"
            print(
                f"{pos.symbol[:11]:<12}"
                f"{fmt_amount(pos.amount):>16}"
                f"{fmt_usd(price):>14}"
                f"{fmt_usd(value):>14}"
                f"{fmt_usd(pos.avg_cost_usd):>14}"
                f"{col}{fmt_usd(unreal) + pct:>18}{RESET}"
            )

        print(f"{DIM}{'-' * 88}{RESET}")
        tcol = pnl_color(total_unreal)
        rcol = pnl_color(total_realized)
        print(
            f"{BOLD}Gesamtwert: {fmt_usd(total_value)}   "
            f"Unrealisiert: {tcol}{fmt_usd(total_unreal)}{RESET}{BOLD}   "
            f"Realisiert: {rcol}{fmt_usd(total_realized)}{RESET}"
        )

    @staticmethod
    def _strip_ansi(text: str) -> str:
        import re
        return re.sub(r"\033\[[0-9;]*m", "", text)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Solana-Wallet-Scanner: erkennt neue Token-Käufe und "
                    "berechnet Gewinn/Verlust (P&L).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("wallet", nargs="?", default=os.environ.get("WALLET_ADDRESS"),
                        help="Solana-Wallet-Adresse (oder Env WALLET_ADDRESS)")
    parser.add_argument("--interval", type=int, default=30,
                        help="Sekunden zwischen den Scans (Standard: 30)")
    parser.add_argument("--once", action="store_true",
                        help="Nur einen einzelnen Scan ausführen (z.B. für cron)")
    parser.add_argument("--test-notify", action="store_true",
                        help="Test-Nachricht an alle konfigurierten Kanäle "
                             "(Telegram/WhatsApp) senden und beenden")
    parser.add_argument("--rpc", default=DEFAULT_RPC_URL,
                        help="Solana-RPC-URL (oder Env SOLANA_RPC_URL)")
    parser.add_argument("--state-file", default=DEFAULT_STATE_FILE,
                        help="Pfad zur State-Datei (JSON)")
    parser.add_argument("--min-value", type=float, default=1.0,
                        help="Mindest-USD-Wert, damit ein neuer Token als Kauf "
                             "gilt (filtert Staub/Airdrops; Standard: 1.0)")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    if args.test_notify:
        notifier = Notifier()
        print(f"{BOLD}{CYAN}Test-Benachrichtigung{RESET}")
        print(f"  Telegram: {'aktiv' if notifier.telegram_enabled else 'aus'}")
        print(f"  WhatsApp: {notifier.wa_provider if notifier.whatsapp_enabled else 'aus'}")
        if not (notifier.telegram_enabled or notifier.whatsapp_enabled):
            print(f"{YELLOW}Kein Kanal konfiguriert (siehe README).{RESET}")
            return 1
        notifier.send(
            f"{GREEN}✅ Test: Solana Wallet Scanner ist verbunden.{RESET}",
            "✅ Test: Solana Wallet Scanner ist verbunden.",
        )
        print(f"{DIM}Gesendet (sofern kein Fehler oben steht).{RESET}")
        return 0

    if not args.wallet:
        print("Fehler: Bitte Wallet-Adresse angeben.\n"
              "  python scanner.py <WALLET_ADRESSE>", file=sys.stderr)
        return 2

    rpc = SolanaRPC(args.rpc)
    prices = PriceProvider()
    notifier = Notifier()
    scanner = WalletScanner(
        wallet=args.wallet,
        rpc=rpc,
        prices=prices,
        notifier=notifier,
        state_file=args.state_file,
        min_value_usd=args.min_value,
    )

    print(f"{BOLD}{CYAN}Solana Wallet Scanner{RESET}")
    print(f"  Wallet:   {args.wallet}")
    print(f"  RPC:      {args.rpc}")
    print(f"  Telegram: {'aktiv' if notifier.telegram_enabled else 'aus'}")
    wa_status = notifier.wa_provider if notifier.whatsapp_enabled else "aus"
    print(f"  WhatsApp: {wa_status}")
    print(f"  Intervall:{'einmalig' if args.once else f' {args.interval}s'}\n")

    if args.once:
        try:
            scanner.scan_once()
        except Exception as exc:  # noqa: BLE001
            print(f"{RED}[Fehler] {exc}{RESET}", file=sys.stderr)
            return 1
        return 0

    # Dauerbetrieb
    try:
        while True:
            try:
                scanner.scan_once()
            except requests.exceptions.RequestException as exc:
                print(f"{YELLOW}[Netzfehler] {exc} – neuer Versuch in "
                      f"{args.interval}s{RESET}")
            except Exception as exc:  # noqa: BLE001
                print(f"{RED}[Fehler] {exc}{RESET}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print(f"\n{DIM}Beendet.{RESET}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
