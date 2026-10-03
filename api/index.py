from http.server import BaseHTTPRequestHandler
import json
import os
import requests


class handler(BaseHTTPRequestHandler):

    def send_telegram(self, chat_id, text):
        token = os.environ["TELEGRAM_BOT_TOKEN"]

        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text[:4000]
            },
            timeout=30
        )

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"NEW ORCHESTRATOR CODE IS LIVE")

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
                return

            if text.startswith("/start"):
                reply = (
                    "🔥 NEW ORCHESTRATOR CODE IS LIVE!\n\n"
                    "Telegram → Vercel connection is working.\n\n"
                    "Pipeline is ready for testing."
                )

            elif text.startswith("/newvideo"):
                idea = text[len("/newvideo"):].strip()

                if not idea:
                    reply = "Use:\n/newvideo <football event or idea>"
                else:
                    reply = "🧠 PIPELINE TEST RECEIVED!\n\nIdea:\n" + idea

                    # Import pipeline only when needed
                    try:
                        from pipeline import run_pipeline

                        self.send_telegram(
                            chat_id,
                            "🧠 Working on it...\n\n"
                            "Gemini → Creative → Production"
                        )

                        reply = run_pipeline(idea)

                    except Exception as e:
                        reply = (
                            "❌ PIPELINE ERROR\n\n"
                            + str(e)
                        )

            else:
                reply = (
                    "⚽ Football AI Orchestrator\n\n"
                    "Use:\n"
                    "/start\n"
                    "/newvideo <football event or idea>"
                )

            self.send_telegram(chat_id, reply)

            self.send_response(200)
            self.end_headers()

        except Exception as e:
            print("ERROR:", str(e))

            self.send_response(200)
            self.end_headers()

