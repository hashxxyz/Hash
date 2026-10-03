import os
import requests
from pipeline import run_pipeline

def send_telegram_message(chat_id, text):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text[:4000]}, timeout=30).raise_for_status()

def handler(request):
    try:
        if request.method != "POST":
            return {"statusCode": 200, "body": "Football AI Orchestrator is running."}
        update = request.get_json() if hasattr(request, "get_json") else request.json
        message = update.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "").strip()
        if not chat_id:
            return {"statusCode": 200, "body": "ok"}
        if text.startswith("/start"):
            reply = "⚽ Football AI Orchestrator\n\nUse /newvideo <football event or idea> to start."
        elif text.startswith("/newvideo"):
            idea = text[len("/newvideo"):].strip()
            reply = "Use: /newvideo <event or idea>" if not idea else run_pipeline(idea)
        else:
            reply = "Use /newvideo <football event or idea>"
        send_telegram_message(chat_id, reply)
        return {"statusCode": 200, "body": "ok"}
    except Exception as e:
        return {"statusCode": 500, "body": str(e)}
