import os
import time
import base64
import sqlite3
import threading
import subprocess
from pathlib import Path

from flask import Flask
from dotenv import load_dotenv
import telebot
from telebot import types

load_dotenv()

BOT_TOKEN = os.getenv("8787085446:AAEsxSSJ4_tbIaEC2sSXswcZTRHNGaiy0mw", "").strip()
ADMIN_ID = int(os.getenv("7045220016", "0"))
PORT = int(os.getenv("PORT", "10000"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing. Add BOT_TOKEN in .env")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)
DB_FILE = "bot.db"

YOUTUBE_LINK = base64.b64decode(
    "aHR0cHM6Ly95b3V0dWJlLmNvbS9AYmxhY2trbm93bGVkZ2VfMTkwP3NpPTlFd2tNUEdiLWxIUnpaZHE="
).decode()

SUPPORT_LINK = base64.b64decode(
    "aHR0cHM6Ly90Lm1lL0JMQUNLX0tub3dsZWRnZV8xOTA="
).decode()

db_lock = threading.Lock()
DB = sqlite3.connect(DB_FILE, check_same_thread=False)
DB.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    joined REAL,
    last_active REAL
)""")
DB.execute("""CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    url TEXT,
    platform TEXT,
    created REAL
)""")
DB.commit()

def add_user(user):
    with db_lock:
        DB.execute("""
            INSERT OR IGNORE INTO users
            (user_id, username, first_name, joined, last_active)
            VALUES (?, ?, ?, ?, ?)
        """, (user.id, user.username or "", user.first_name or "", time.time(), time.time()))
        DB.execute("""
            UPDATE users SET username=?, first_name=?, last_active=?
            WHERE user_id=?
        """, (user.username or "", user.first_name or "", time.time(), user.id))
        DB.commit()

def add_download(user_id, url, platform):
    with db_lock:
        DB.execute(
            "INSERT INTO downloads (user_id,url,platform,created) VALUES (?,?,?,?)",
            (user_id, url, platform, time.time())
        )
        DB.commit()

app = Flask(__name__)

@app.route("/")
def home():
    return "BLACK KNOWLEDGE Downloader Bot is Online!"

@app.route("/health")
def health():
    return "OK"

def keep_alive():
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

def start_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("📢 SUBSCRIBE CHANNEL", url=YOUTUBE_LINK),
        types.InlineKeyboardButton("📚 ALL TUTORIALS", url=YOUTUBE_LINK),
        types.InlineKeyboardButton("👤 CONTACT OWNER", url=SUPPORT_LINK)
    )
    return keyboard

@bot.message_handler(commands=["start"])
def start(message):
    add_user(message.from_user)
    text = (
        "╔══════════════════════════╗\n"
        "     <b>BLACK KNOWLEDGE</b>\n"
        "╚══════════════════════════╝\n\n"
        "👋 <b>Welcome!</b>\n\n"
        "🎬 Instagram & Facebook Downloader\n\n"
        "🔗 Send a video/reel link.\n\n"
        "✨ <b>Features</b>\n"
        "• HD Video • MP4 • Audio\n"
        "• Thumbnail • History\n"
        "• Fast Processing\n\n"
        "👑 <b>@BLACK_KNOWLEDGE_190</b>"
    )
    bot.send_message(message.chat.id, text, reply_markup=start_keyboard())

def detect_platform(url):
    u = url.lower()
    if "instagram.com" in u:
        return "Instagram"
    if "facebook.com" in u or "fb.watch" in u:
        return "Facebook"
    return None

def valid_url(url):
    return detect_platform(url) is not None

def download_video(url, output_template, audio=False, hd=False):
    if audio:
        command = [
            "yt-dlp", "--no-playlist", "-x",
            "--audio-format", "mp3", "-o", output_template, url
        ]
    else:
        fmt = "bestvideo*+bestaudio/best" if hd else "best"
        command = [
            "yt-dlp", "--no-playlist", "-f", fmt,
            "--merge-output-format", "mp4",
            "--write-thumbnail", "--convert-thumbnails", "jpg",
            "-o", output_template, url
        ]

    result = subprocess.run(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-1500:])

def cleanup_files(prefix):
    for f in DOWNLOAD_DIR.glob(f"{prefix}.*"):
        try:
            os.remove(f)
        except OSError:
            pass

def process_download(message, url, hd=False, audio=False):
    user_id = message.from_user.id
    status = bot.reply_to(message, "🔎 <b>Analyzing...</b>")
    platform = detect_platform(url)
    prefix = f"{user_id}_{int(time.time())}"
    output = str(DOWNLOAD_DIR / f"{prefix}.%(ext)s")

    try:
        bot.edit_message_text(
            f"🔎 <b>Analyzing...</b>\n━━━━━━━━━━━━━━\nPlatform: <b>{platform}</b>",
            message.chat.id, status.message_id
        )
        time.sleep(0.5)

        bot.edit_message_text(
            "⬇️ <b>Downloading (50%)...</b>\n━━━━━━━━━━━━━━\nPlease wait...",
            message.chat.id, status.message_id
        )

        download_video(url, output, audio=audio, hd=hd)

        media_file = None
        for f in DOWNLOAD_DIR.glob(f"{prefix}.*"):
            if f.suffix.lower() in (".mp4", ".mkv", ".webm", ".mp3", ".m4a"):
                media_file = f
                break

        if not media_file:
            raise FileNotFoundError("Downloaded media not found.")

        bot.edit_message_text(
            "⬆️ <b>Uploading (100%)...</b>\n━━━━━━━━━━━━━━\nAlmost done...",
            message.chat.id, status.message_id
        )

        with open(media_file, "rb") as media:
            if audio:
                bot.send_audio(
                    message.chat.id, media,
                    caption="Downloaded Successfully! Power"
                )
            else:
                bot.send_video(
                    message.chat.id, media,
                    caption="Downloaded Successfully! Power",
                    supports_streaming=True
                )

        add_download(user_id, url, platform)
        bot.delete_message(message.chat.id, status.message_id)

    except Exception:
        try:
            bot.edit_message_text(
                "❌ <b>Download Failed</b>\n\n"
                "The link may be private, invalid, unsupported, "
                "or temporarily unavailable.\n\n🔄 Please try again.",
                message.chat.id, status.message_id
            )
        except Exception:
            pass
    finally:
        cleanup_files(prefix)

user_last_request = {}
RATE_LIMIT_SECONDS = 15

def rate_limited(user_id):
    now = time.time()
    last = user_last_request.get(user_id, 0)
    if now - last < RATE_LIMIT_SECONDS:
        return True
    user_last_request[user_id] = now
    return False

@bot.message_handler(func=lambda m: m.text and not m.text.startswith("/"))
def receive_url(message):
    add_user(message.from_user)
    url = message.text.strip()

    if rate_limited(message.from_user.id):
        bot.reply_to(message, "⏳ <b>Please wait!</b> You are sending requests too quickly.")
        return

    if not valid_url(url):
        bot.reply_to(
            message,
            "❌ <b>Invalid Link</b>\n\nSupported:\n• Instagram Reel\n• Facebook Video"
        )
        return

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("🎥 MP4", callback_data=f"mp4:{url}"),
        types.InlineKeyboardButton("🔥 HD", callback_data=f"hd:{url}"),
        types.InlineKeyboardButton("🎵 MP3", callback_data=f"mp3:{url}")
    )
    bot.reply_to(
        message,
        f"✅ <b>Link Detected!</b>\n\n🌐 Platform: <b>{detect_platform(url)}</b>\n\nChoose quality:",
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith(("mp4:", "hd:", "mp3:")))
def download_callback(call):
    action, url = call.data.split(":", 1)
    bot.answer_callback_query(call.id, "Starting download...")
    args = (call.message, url, action == "hd", action == "mp3")
    threading.Thread(target=process_download, args=args, daemon=True).start()

@bot.callback_query_handler(func=lambda call: call.data == "history")
def history(call):
    rows = DB.execute(
        "SELECT platform,created FROM downloads WHERE user_id=? ORDER BY created DESC LIMIT 10",
        (call.from_user.id,)
    ).fetchall()
    if not rows:
        text = "📥 <b>Download History</b>\n\nNo downloads yet."
    else:
        text = "📥 <b>Download History</b>\n\n"
        for i, (platform, created) in enumerate(rows, 1):
            text += f"{i}. {platform} — {time.strftime('%d/%m/%Y', time.localtime(created))}\n"
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, text)

@bot.callback_query_handler(func=lambda call: call.data == "clear_history")
def clear_history(call):
    with db_lock:
        DB.execute("DELETE FROM downloads WHERE user_id=?", (call.from_user.id,))
        DB.commit()
    bot.answer_callback_query(call.id, "History cleared!")
    bot.send_message(call.message.chat.id, "🗑️ <b>Download history cleared.</b>")

@bot.callback_query_handler(func=lambda call: call.data == "myinfo")
def my_info(call):
    count = DB.execute(
        "SELECT COUNT(*) FROM downloads WHERE user_id=?", (call.from_user.id,)
    ).fetchone()[0]
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        f"👤 <b>Your Info</b>\n\n"
        f"🆔 ID: <code>{call.from_user.id}</code>\n"
        f"👤 Username: @{call.from_user.username or 'None'}\n"
        f"📥 Downloads: <b>{count}</b>"
    )

def is_admin(user_id):
    return ADMIN_ID != 0 and user_id == ADMIN_ID

@bot.message_handler(commands=["stats"])
def stats(message):
    if not is_admin(message.from_user.id):
        return
    users = DB.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    downloads = DB.execute("SELECT COUNT(*) FROM downloads").fetchone()[0]
    active = DB.execute(
        "SELECT COUNT(*) FROM users WHERE last_active > ?", (time.time() - 86400,)
    ).fetchone()[0]
    bot.reply_to(
        message,
        f"📊 <b>ADMIN STATISTICS</b>\n\n"
        f"👥 Total Users: <b>{users}</b>\n"
        f"📥 Total Downloads: <b>{downloads}</b>\n"
        f"🟢 Active 24h: <b>{active}</b>"
    )

@bot.message_handler(commands=["users"])
def users_command(message):
    if not is_admin(message.from_user.id):
        return
    rows = DB.execute(
        "SELECT user_id,username FROM users ORDER BY last_active DESC LIMIT 50"
    ).fetchall()
    text = "👥 <b>Users</b>\n\n"
    for user_id, username in rows:
        text += f"• <code>{user_id}</code> @{username or 'None'}\n"
    bot.reply_to(message, text[:4000])

@bot.message_handler(commands=["broadcast"])
def broadcast(message):
    if not is_admin(message.from_user.id):
        return
    text = message.text[len("/broadcast"):].strip()
    if not text:
        bot.reply_to(message, "Usage: <code>/broadcast Your message</code>")
        return
    rows = DB.execute("SELECT user_id FROM users").fetchall()
    sent = 0
    for (user_id,) in rows:
        try:
            bot.send_message(user_id, text)
            sent += 1
            time.sleep(0.05)
        except Exception:
            pass
    bot.reply_to(message, f"📢 Broadcast completed.\n\n✅ Sent: <b>{sent}</b>")

@bot.message_handler(commands=["admin"])
def admin_panel(message):
    if not is_admin(message.from_user.id):
        return
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"),
        types.InlineKeyboardButton("👥 Users", callback_data="admin_users")
    )
    keyboard.add(types.InlineKeyboardButton("📢 Broadcast Help", callback_data="broadcast_help"))
    bot.reply_to(message, "👑 <b>ADMIN PANEL</b>\n\nManage your downloader bot:", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data in ("admin_stats", "admin_users", "broadcast_help"))
def admin_callbacks(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Not authorized.", show_alert=True)
        return

    if call.data == "admin_stats":
        users = DB.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        downloads = DB.execute("SELECT COUNT(*) FROM downloads").fetchone()[0]
        active = DB.execute(
            "SELECT COUNT(*) FROM users WHERE last_active > ?", (time.time() - 86400,)
        ).fetchone()[0]
        text = f"📊 <b>ADMIN STATISTICS</b>\n\n👥 Users: <b>{users}</b>\n📥 Downloads: <b>{downloads}</b>\n🟢 Active 24h: <b>{active}</b>"
    elif call.data == "admin_users":
        count = DB.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        text = f"👥 <b>USER MANAGEMENT</b>\n\nTotal registered users: <b>{count}</b>\n\nUse /users to view users."
    else:
        text = "📢 <b>BROADCAST</b>\n\nUse:\n<code>/broadcast Your message</code>"

    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, text)

if __name__ == "__main__":
    threading.Thread(target=keep_alive, daemon=True).start()
    print("BLACK KNOWLEDGE DOWNLOADER BOT STARTED")
    bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
