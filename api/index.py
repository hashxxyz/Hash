from http.server import BaseHTTPRequestHandler
import html
import json
import os
import re
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

COMMANDS = {"/tips", "/football", "/basketball", "/safe", "/goals", "/btts", "/acca",
            "/over", "/under", "/corners", "/1x2", "/dc", "/firsthalf"}
_SEEN = {}  # update_id -> time; stops duplicate replies when Telegram re-sends a webhook

MENU = ("/tips — everything (all sections)\n/football — football only\n/basketball — basketball only\n"
        "/over — over goals\n/under — under goals\n/corners — corners\n/1x2 — match result\n"
        "/dc — double chance\n/firsthalf — 1st half\n/goals — over + under + 1st half\n/btts — both teams to score\n"
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
    if update_id is None:
        return False
    now = time.time()
    for k in [k for k, t in _SEEN.items() if now - t > 600]:
        _SEEN.pop(k, None)
    if update_id in _SEEN:
        return True
    _SEEN[update_id] = now
    return False


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
        self.wfile.write(b"AI Football + Basketball Betting Guru is LIVE")

    def do_POST(self):
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
