from http.server import BaseHTTPRequestHandler
import json
import os
import requests


class handler(BaseHTTPRequestHandler):

    def send_telegram(self, chat_id, text):
        token = os.environ["TELEGRAM_BOT_TOKEN"]
        max_length = 3900

        parts = []
        while len(text) > max_length:
            split_at = text.rfind("\n", 0, max_length)
            if split_at == -1:
                split_at = text.rfind(" ", 0, max_length)
            if split_at == -1:
                split_at = max_length

            parts.append(text[:split_at])
            text = text[split_at:].lstrip()

        if text:
            parts.append(text)

        total = len(parts)

        for i, part in enumerate(parts, 1):
            if total > 1:
                part = f"📄 Part {i}/{total}\n\n{part}"

            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": part},
                timeout=30,
            )
            response.raise_for_status()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"AI Football Betting Guru is LIVE")

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            update = json.loads(body.decode("utf-8"))

            message = update.get("message", {})
            chat_id = (message.get("chat") or {}).get("id")
            text = (message.get("text") or "").strip()

            if not chat_id:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")
                return

            command = text.split()[0].split("@")[0].lower() if text else ""

            if command == "/start":
                self.send_telegram(
                    chat_id,
                    "⚽ AI FOOTBALL BETTING GURU\n\n"
                    "I automatically scan today's football data and "
                    "produce probability-based betting analysis.\n\n"
                    "Commands:\n"
                    "/tips — strongest overall picks\n"
                    "/safe — conservative picks\n"
                    "/goals — goals markets\n"
                    "/btts — BTTS picks\n"
                    "/acca — up to 3 strongest legs\n"
                    "/help — command list\n\n"
                    "⚠️ No bet is guaranteed."
                )

            elif command in {"/tips", "/safe", "/goals", "/btts", "/acca"}:
                mode = command[1:]

                self.send_telegram(
                    chat_id,
                    "🧠 Scanning today's football...\n\n"
                    "Fixtures → predictions → verified odds → AI analysis"
                )

                try:
                    from pipeline import run_pipeline
                    result = run_pipeline(mode=mode)
                    self.send_telegram(chat_id, result)
                except Exception as e:
                    self.send_telegram(
                        chat_id,
                        "❌ ANALYSIS ERROR\n\n"
                        + str(e)
                    )

            elif command == "/help":
                self.send_telegram(
                    chat_id,
                    "⚽ AI FOOTBALL BETTING GURU\n\n"
                    "/tips — best overall opportunities\n"
                    "/safe — lower-risk opportunities\n"
                    "/goals — goals markets only\n"
                    "/btts — BTTS only\n"
                    "/acca — maximum 3-leg accumulator\n\n"
                    "The bot finds today's fixtures automatically. "
                    "You do not need to send match names.\n\n"
                    "⚠️ Probability-based analysis, not guaranteed results."
                )

            else:
                self.send_telegram(
                    chat_id,
                    "Use /tips to scan today's football automatically.\n\n"
                    "Other commands:\n"
                    "/safe\n"
                    "/goals\n"
                    "/btts\n"
                    "/acca\n"
                    "/help"
                )

            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")

        except Exception as e:
            print("ERROR:", str(e))

            # Always acknowledge Telegram.
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
