from http.server import BaseHTTPRequestHandler
import json
import os
import requests


class handler(BaseHTTPRequestHandler):

    def send_telegram(self, chat_id, text):
        token = os.environ["TELEGRAM_BOT_TOKEN"]

        # Telegram message limit is about 4096 characters.
        # Keep a safety margin and split long AI responses.
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
                json={
                    "chat_id": chat_id,
                    "text": part
                },
                timeout=30
            )

            response.raise_for_status()

    def do_GET(self):

        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/plain"
        )
        self.end_headers()

        self.wfile.write(
            b"Football AI Orchestrator is LIVE"
        )

    def do_POST(self):

        try:

            length = int(
                self.headers.get(
                    "Content-Length",
                    0
                )
            )

            body = self.rfile.read(length)

            update = json.loads(
                body.decode("utf-8")
            )

            message = update.get(
                "message",
                {}
            )

            chat_id = message.get(
                "chat",
                {}
            ).get("id")

            text = message.get(
                "text",
                ""
            ).strip()

            if not chat_id:

                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")
                return

            # START
            if text.startswith("/start"):

                reply = (
                    "⚽ Football AI Orchestrator\n\n"
                    "🔥 Bot connected successfully!\n\n"
                    "Pipeline:\n"
                    "Research → Comedy → Production\n\n"
                    "Use:\n"
                    "/newvideo <football situation>"
                )

                self.send_telegram(
                    chat_id,
                    reply
                )

            # NEW VIDEO
            elif text.startswith("/newvideo"):

                idea = text[
                    len("/newvideo"):
                ].strip()

                if not idea:

                    self.send_telegram(
                        chat_id,
                        "Use:\n\n"
                        "/newvideo <football situation>"
                    )

                else:

                    # Tell the user the job has started.
                    self.send_telegram(
                        chat_id,
                        "🧠 Working on it...\n\n"
                        "Football research → "
                        "Comedy concept → "
                        "Production blueprint"
                    )

                    try:

                        # Import only when needed.
                        # This keeps /start working even if
                        # an AI provider has a problem.
                        from pipeline import run_pipeline

                        result = run_pipeline(
                            idea
                        )

                        self.send_telegram(
                            chat_id,
                            result
                        )

                    except Exception as e:

                        error_message = (
                            "❌ PIPELINE ERROR\n\n"
                            + str(e)
                        )

                        self.send_telegram(
                            chat_id,
                            error_message
                        )

            # HELP
            elif text.startswith("/help"):

                reply = (
                    "⚽ Football AI Orchestrator\n\n"
                    "Commands:\n\n"
                    "/start\n"
                    "Check the bot connection.\n\n"
                    "/newvideo <football situation>\n"
                    "Run the full AI production pipeline.\n\n"
                    "/help\n"
                    "Show this help."
                )

                self.send_telegram(
                    chat_id,
                    reply
                )

            # UNKNOWN COMMAND
            else:

                self.send_telegram(
                    chat_id,
                    "Use:\n\n"
                    "/start\n"
                    "/newvideo <football situation>\n"
                    "/help"
                )

            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/plain"
            )
            self.end_headers()

            self.wfile.write(
                b"ok"
            )

        except Exception as e:

            print(
                "ERROR:",
                str(e)
            )

            # Always acknowledge Telegram so it
            # doesn't repeatedly resend the update.
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/plain"
            )
            self.end_headers()

            self.wfile.write(
                b"ok"
            )
