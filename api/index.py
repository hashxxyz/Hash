from http.server import BaseHTTPRequestHandler
import json
import os
import requests

from pipeline import run_pipeline


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Football AI Orchestrator is running.")

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            update = json.loads(body.decode("utf-8"))

            message = update.get("message", {})
            chat_id = message.get("chat", {}).get("id")
            text = message.get("text", "").strip()

            if not chat_id:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")
                return

            if text.startswith("/start"):
                reply = (
                    "⚽ Football AI Orchestrator\n\n"
                    "Use /newvideo <football event or idea> to start."
                )

            elif text.startswith("/newvideo"):
                idea = text[len("/newvideo"):].strip()

                if not idea:
                    reply = "Use: /newvideo <event or idea>"
                else:
                    reply = run_pipeline(idea)

            else:
                reply = "Use /newvideo <football event or idea>"

            token = os.getenv("TELEGRAM_BOT_TOKEN")

            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": reply[:4000]
                },
                timeout=30
            ).raise_for_status()

            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(str(e).encode("utf-8"))
        
