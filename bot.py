import os
import json
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from openai import OpenAI

# گرفتن کلیدها از متغیر محیطی
TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")

client = OpenAI(api_key=OPENAI_KEY)

# فایل دیتای ویدیوها
VIDEO_FILE = "videos.json"
if not os.path.exists(VIDEO_FILE):
    with open(VIDEO_FILE, "w") as f:
        json.dump({}, f)

def load_videos():
    with open(VIDEO_FILE, "r") as f:
        return json.load(f)

def save_videos(data):
    with open(VIDEO_FILE, "w") as f:
        json.dump(data, f, indent=2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام! نام حرکت بدنسازی رو بفرست تا ویدیو و توضیح بدم.")

async def setvideo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) != str(ADMIN_USER_ID):
        await update.message.reply_text("شما اجازه این کار رو ندارید.")
        return
    try:
        move = context.args[0]
        link = context.args[1]
        videos = load_videos()
        videos[move.lower()] = link
        save_videos(videos)
        await update.message.reply_text(f"✅ ویدیو برای {move} ذخیره شد.")
    except:
        await update.message.reply_text("❌ دستور اشتباه. نمونه: /setvideo اسکوات لینک")

async def handle_move(update: Update, context: ContextTypes.DEFAULT_TYPE):
    move = update.message.text.strip().lower()
    videos = load_videos()

    # گرفتن توضیح از هوش مصنوعی
    try:
        prompt = f"یک توضیح آموزشی کامل و کوتاه درباره حرکت بدنسازی {move} بده."
        completion = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt
        )
        ai_text = completion.output_text
    except Exception as e:
        ai_text = f"⚠️ خطا در گرفتن توضیح: {e}"

    # ارسال ویدیو یا لینک
    if move in videos:
        link = videos[move]
        try:
            r = requests.get(link, stream=True, timeout=10)
            if r.status_code == 200 and "video" in r.headers.get("Content-Type", ""):
                filename = f"{move}.mp4"
                with open(filename, "wb") as f:
                    for chunk in r.iter_content(1024):
                        f.write(chunk)
                await update.message.reply_video(video=open(filename, "rb"), caption=ai_text)
                os.remove(filename)
            else:
                await update.message.reply_text(f"{ai_text}\n🎥 لینک ویدیو: {link}")
        except:
            await update.message.reply_text(f"{ai_text}\n🎥 لینک ویدیو: {link}")
    else:
        await update.message.reply_text(f"ℹ️ ویدیویی برای {move} ثبت نشده.\n\n{ai_text}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setvideo", setvideo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_move))
    print("🤖 Fitness AI bot is running (polling)…")
    app.run_polling()
