import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pipeline import run_pipeline

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚽ Football AI Orchestrator\n\n"
        "Use /newvideo <football event or idea> to start a project."
    )

async def newvideo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idea = " ".join(context.args).strip()
    if not idea:
        await update.message.reply_text("Use: /newvideo <event or idea>")
        return
    await update.message.reply_text("🤖 Agents are working...")
    try:
        result = run_pipeline(idea)
        await update.message.reply_text(result[:4000])
    except Exception as e:
        await update.message.reply_text(f"⚠️ Pipeline error: {e}")

def main():
    if not TOKEN:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newvideo", newvideo))
    app.run_polling()

if __name__ == "__main__":
    main()
