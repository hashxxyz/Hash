from http.server import BaseHTTPRequestHandler
import hmac
import html
import json
import os
import re
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

COMMANDS = {"/tips", "/football", "/basketball", "/safe", "/goals", "/btts", "/acca", "/totals",
            "/over", "/under", "/bbover", "/bbunder", "/1x2", "/dc"}

MENU = ("/tips — everything (all sections)\n/totals — all over/under (football + basketball)\n"
        "/football — football only\n/basketball — basketball only\n"
        "/over — football over goals\n/under — football under goals\n/goals — football over + under\n"
        "/bbover — basketball over\n/bbunder — basketball under\n"
        "/1x2 — match result\n/dc — double chance\n/btts — both teams to score\n"
        "/safe — conservative picks\n/acca — best 3-leg accumulator")
START_TEXT = "⚽🏀 <b>AI BETTING GURU</b>\n\nI scan today's fixtures and odds and send probability-based tips.\n\n" + MENU + "\n\n⚠️ No bet is guaranteed."
HELP_TEXT = "⚽🏀 <b>AI BETTING GURU</b>\n\n" + MENU + "\n\n⚠️ Probability-based analysis, not guaranteed results."
FALLBACK_TEXT = "Use /tips to scan today's games.\n\n" + MENU


def scrub(text):
    from agents import scrub as _scrub
    return _scrub(text)


def is_allowed(chat_id):
    raw = os.environ.get("ALLOWED_CHAT_IDS", "").strip()
    if not raw:
        return True  # not configured = open bot
    return str(chat_id) in {x.strip() for x in raw.split(",")}


def is_duplicate(update_id):
    """True when this Telegram update was already handled (Telegram re-sends webhooks it thinks failed)."""
    if update_id is None:
        return False
    import store
    return not store.claim(f"guru:update:{update_id}", 600)


def secret_ok(headers):
    """If TELEGRAM_WEBHOOK_SECRET is set, only accept requests carrying it (set it with setWebhook secret_token)."""
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    if not secret:
        return True
    return hmac.compare_digest(headers.get("X-Telegram-Bot-Api-Secret-Token", ""), secret)


class handler(BaseHTTPRequestHandler):
    def send_telegram(self, chat_id, text):
        token = os.environ["TELEGRAM_BOT_TOKEN"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        while text:
            part = text[:3900]
            if len(text) > 3900:
                cut = part.rfind("\n\n")
                if cut < 500:
                    cut = part.rfind("\n")
                if cut > 500:
                    part = part[:cut]
            text = text[len(part):].lstrip()
            r = requests.post(url, json={"chat_id": chat_id, "text": part, "parse_mode": "HTML"}, timeout=30)
            if r.status_code == 400:  # bad HTML entity: resend as plain text instead of losing the message
                plain = re.sub(r"<[^>]+>", "", part)
                r = requests.post(url, json={"chat_id": chat_id, "text": html.unescape(plain)}, timeout=30)
            r.raise_for_status()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"AI Betting Guru is LIVE")

    def do_POST(self):
        if not secret_ok(self.headers):
            self.send_response(403)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"forbidden")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            update = json.loads(self.rfile.read(length).decode())
            if is_duplicate(update.get("update_id")):
                self._ok()
                return
            msg = update.get("message", {})
            chat_id = (msg.get("chat") or {}).get("id")
            text = (msg.get("text") or "").strip()
            if not chat_id:
                self._ok()
                return
            if not is_allowed(chat_id):
                self.send_telegram(chat_id, "🔒 This is a private bot.")
                self._ok()
                return

            cmd = text.split()[0].split("@")[0].lower() if text else ""
            if cmd == "/start":
                self.send_telegram(chat_id, START_TEXT)
            elif cmd in COMMANDS:
                mode = cmd[1:]
                label = "football + basketball" if mode in {"tips", "acca"} else mode
                self.send_telegram(chat_id, f"🧠 Scanning today's {label}...\n\nData → research → AI analysis → final picks")
                try:
                    from pipeline import run_pipeline
                    self.send_telegram(chat_id, run_pipeline(mode))
                except Exception as e:
                    print("PIPELINE ERROR:", scrub(e))
                    self.send_telegram(chat_id, "❌ Analysis failed this time. Please try again in a minute.")
            elif cmd == "/help":
                self.send_telegram(chat_id, HELP_TEXT)
            else:
                self.send_telegram(chat_id, FALLBACK_TEXT)
            self._ok()
        except Exception as e:
            print("ERROR:", scrub(e))
            self._ok()

    def _ok(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")
