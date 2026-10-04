from http.server import BaseHTTPRequestHandler
import json, os, requests

class handler(BaseHTTPRequestHandler):
    def send_telegram(self, chat_id, text):
        token = os.environ["TELEGRAM_BOT_TOKEN"]
        while text:
            part = text[:3900]
            if len(text) > 3900:
                cut = part.rfind("\n")
                if cut > 500: part = part[:cut]
            text = text[len(part):].lstrip()
            r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": part}, timeout=30)
            r.raise_for_status()

    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers(); self.wfile.write(b"AI Football + Basketball Betting Guru is LIVE")

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0)); update = json.loads(self.rfile.read(length).decode())
            msg = update.get("message", {}); chat_id = (msg.get("chat") or {}).get("id"); text = (msg.get("text") or "").strip()
            if not chat_id: self._ok(); return
            cmd = text.split()[0].split("@")[0].lower() if text else ""
            if cmd == "/start":
                self.send_telegram(chat_id, "⚽🏀 AI BETTING GURU\n\nI automatically scan today's football + basketball data and produce probability-based tips.\n\n/tips — both sports\n/football — football only\n/basketball — basketball only\n/safe — conservative picks\n/goals — football goals\n/btts — football BTTS\n/acca — strongest combined legs\n/help — commands\n\n⚠️ No bet is guaranteed.")
            elif cmd in {"/tips", "/football", "/basketball", "/safe", "/goals", "/btts", "/acca"}:
                mode = cmd[1:]
                self.send_telegram(chat_id, "🧠 Scanning today's " + ("football + basketball" if mode == "tips" else mode) + "...\n\nData → research → AI analysis → final picks")
                try:
                    from pipeline import run_pipeline
                    self.send_telegram(chat_id, run_pipeline(mode))
                except Exception as e:
                    self.send_telegram(chat_id, "❌ ANALYSIS ERROR\n\n" + str(e))
            elif cmd == "/help":
                self.send_telegram(chat_id, "⚽🏀 AI BETTING GURU\n\n/tips — football + basketball\n/football — football only\n/basketball — basketball only\n/safe — conservative\n/goals — football goals\n/btts — football BTTS\n/acca — max 3 combined legs\n\nThe bot finds today's fixtures automatically.\n⚠️ Probability-based analysis, not guaranteed results.")
            else:
                self.send_telegram(chat_id, "Use /tips to scan football + basketball automatically.\n\n/football\n/basketball\n/safe\n/goals\n/btts\n/acca\n/help")
            self._ok()
        except Exception as e:
            print("ERROR:", e); self._ok()

    def _ok(self):
        self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers(); self.wfile.write(b"ok")
