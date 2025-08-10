import os
import json
import requests
from urllib.parse import quote_plus

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# ---------- OpenAI ----------
from openai import OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------- Env ----------
TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_BASE = os.getenv("WEBHOOK_BASE")  # مثل: https://your-app.onrender.com
PORT = int(os.getenv("PORT", "10000"))   # Render خودش PORT ست می‌کند
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")  # اختیاری
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

# ---------- DB (optional: ویدیوهای اختصاصی ذخیره خودت) ----------
VIDEO_FILE = "videos.json"
if not os.path.exists(VIDEO_FILE):
    with open(VIDEO_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f, ensure_ascii=False, indent=2)

def load_videos():
    try:
        with open(VIDEO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_videos(data):
    with open(VIDEO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ---------- نگاشت فارسی → انگلیسی + fallback ترجمه ----------
FA_EN = {
    "اسکوات": "squat",
    "ددلیفت": "deadlift",
    "پرس سینه": "bench press",
    "زیربغل": "lat pulldown",
    "بارفیکس": "pull up",
    "جلو بازو": "bicep curl",
    "هامر": "hammer curl",
    "لانج": "lunge",
    "پرس پا": "leg press",
    "شنا سوئدی": "push up",
    "سرشانه": "shoulder press",
    "پلانک": "plank",
    "اسکوات بلغاری": "bulgarian split squat",
    "ددلیفت رومانیایی": "romanian deadlift",
    "پرس سرشانه هالتر": "overhead press",
    "لت پول داون": "lat pulldown",
}

def to_search_query(q: str) -> str:
    q = (q or "").strip().lower()
    if q in FA_EN:
        return FA_EN[q]
    # ترجمهٔ خیلی کوتاه به انگلیسی اگر در نگاشت نبود
    try:
        tr_prompt = f"Translate this gym exercise to a short English search keyword (1-3 words), no extra text:\n{q}"
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",  # در دسترس‌تر
            messages=[{"role": "user", "content": tr_prompt}],
            temperature=0,
            max_tokens=10,
        )
        kw = (resp.choices[0].message.content or "").strip().lower()
        return kw if kw and len(kw) <= 40 else q
    except Exception:
        return q

# ---------- AI متن توضیح ----------
def get_ai_text(move: str) -> str:
    prompt = (
        f"برای حرکت بدنسازی «{move}» یک راهنمای کوتاه و کاربردی فارسی بده: "
        "عضلات هدف، مراحل اجرا، تنفس، نکات ایمنی، خطاهای رایج، و الگوی ست/تکرار برای مبتدی."
    )
    try:
        # تلاش با مدل سریع‌تر/به‌صرفه
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a concise Persian strength coach."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.5,
                max_tokens=350,
            )
        except Exception:
            resp = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a concise Persian strength coach."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.5,
                max_tokens=350,
            )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"توضیح پایه: فرم درست، تنفس کنترل‌شده، ایمنی و افزایش تدریجی بار را رعایت کن. (AI: {e})"

# ---------- گرفتن ویدیو از Pexels (MP4 مستقیم ≤720p) ----------
def search_pexels_video(query: str) -> str | None:
    if not PEXELS_API_KEY:
        return None
    try:
        q = to_search_query(query)
        r = requests.get(
            "https://api.pexels.com/videos/search",
            params={"query": q, "per_page": 3},
            headers={"Authorization": PEXELS_API_KEY},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        for v in data.get("videos", []):
            files = sorted(v.get("video_files", []), key=lambda f: (f.get("height") or 0))
            for f in files:
                if f.get("file_type") == "video/mp4" and (f.get("height") or 0) <= 720:
                    return f.get("link")
        return None
    except Exception:
        return None

def make_search_links(move: str) -> tuple[str, str]:
    q = to_search_query(move)
    qp = quote_plus(q)
    aparat = f"https://www.aparat.com/search/{qp}"
    youtube = f"https://www.youtube.com/results?search_query={qp}"
    return aparat, youtube

# ---------- اوامر ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! 👋 نام حرکت بدنسازی رو بفرست تا ویدیو + توضیح تخصصی بدم.\n"
        "اوامر ادمین:\n"
        "/setvideo <حرکت> <URL> — ثبت/تغییر لینک ویدیو\n"
        "/listvideos — لیست حرکات دارای ویدیو\n"
        "/help — راهنما"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "نام حرکت را بفرست (مثل اسکوات/ددلیفت/پرس سینه). اگر ویدیو ثبت شده باشد، فایل ویدیو آپلود می‌شود.\n"
        "ادمین: /setvideo اسکوات https://example.com/squat.mp4"
    )

async def list_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = load_videos()
    if not db:
        await update.message.reply_text("هنوز ویدیویی ثبت نشده.")
        return
    lines = [f"• {k} -> {v}" for k, v in db.items()]
    await update.message.reply_text("ویدیوهای ثبت‌شده:\n" + "\n".join(lines))

async def setvideo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ADMIN_USER_ID and str(update.effective_user.id) != str(ADMIN_USER_ID):
        await update.message.reply_text("فقط ادمین اجازه این دستور را دارد.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("فرمت صحیح: /setvideo <نام حرکت> <URL>")
        return
    move = args[0].strip().lower()
    url = args[1]
    if not url.startswith("http"):
        await update.message.reply_text("URL معتبر نیست (با http/https شروع شود).")
        return
    db = load_videos()
    db[move] = url
    save_videos(db)
    await update.message.reply_text(f"ویدیو برای «{move}» ثبت/به‌روزرسانی شد ✅")

# ---------- هندلر اصلی ----------
async def handle_move(update: Update, context: ContextTypes.DEFAULT_TYPE):
    move = (update.message.text or "").strip().lower()
    if not move:
        return

    ai_text = get_ai_text(move)

    # ۱) اگر ویدیوی اختصاصی ثبت شده:
    videos = load_videos()
    video_url = videos.get(move)

    # ۲) در غیر این صورت از Pexels بگیر
    if not video_url:
        video_url = search_pexels_video(move)

    if video_url:
        # تلاش برای دانلود و آپلود (حد 45MB)
        try:
            r = requests.get(video_url, stream=True, timeout=25)
            r.raise_for_status()
            size = 0
            filename = f"{move}.mp4"
            with open(filename, "wb") as f:
                for chunk in r.iter_content(1024 * 256):
                    if chunk:
                        f.write(chunk)
                        size += len(chunk)
                        if size > 45 * 1024 * 1024:
                            raise RuntimeError("video too large")
            await update.message.reply_video(video=open(filename, "rb"), caption=ai_text[:1024])
        except Exception:
            aparat, yt = make_search_links(move)
            await update.message.reply_text(
                f"{ai_text}\n"
                f"🎥 لینک ویدیو: {video_url}\n\n"
                f"🔎 آپارات: {aparat}\n"
                f"🔎 YouTube: {yt}"
            )
        finally:
            try:
                os.remove(filename)
            except Exception:
                pass
    else:
        # ۳) هیچ ویدیویی پیدا نشد → لینک جست‌وجو
        aparat, yt = make_search_links(move)
        await update.message.reply_text(
            f"{ai_text}\n\n"
            f"🔎 آپارات: {aparat}\n"
            f"🔎 YouTube: {yt}"
        )

# ---------- اجرای وب‌هوک برای Render Web Service ----------
if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN تنظیم نشده.")
    if not WEBHOOK_BASE or not WEBHOOK_BASE.startswith("http"):
        raise RuntimeError("WEBHOOK_BASE تنظیم نشده یا معتبر نیست. مثال: https://your-app.onrender.com")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("listvideos", list_videos))
    app.add_handler(CommandHandler("setvideo", setvideo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_move))

    webhook_path = f"/{TOKEN}"
    print("🚀 Running via webhook ...")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=WEBHOOK_BASE + webhook_path,
    )
