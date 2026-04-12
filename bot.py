import os
import sqlite3
import logging
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def get_db():
    conn = sqlite3.connect('littlemoon.db', timeout=20.0)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    db = get_db()
    c = db.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0, level TEXT DEFAULT 'Normal')")
    c.execute("CREATE TABLE IF NOT EXISTS categories (name TEXT PRIMARY KEY)")
    c.execute("CREATE TABLE IF NOT EXISTS products (shortcode TEXT PRIMARY KEY, category TEXT, name TEXT, n_price REAL, s_price REAL, g_price REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS stocks (id INTEGER PRIMARY KEY AUTOINCREMENT, shortcode TEXT, code_value TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT, amount REAL, detail TEXT, date TEXT)")
    c.execute("INSERT OR IGNORE INTO categories (name) VALUES ('TikTok Boost')")
    db.commit()

init_db()

def main_menu(uid):
    kb = [[KeyboardButton("🛒 Buy Product"), KeyboardButton("👤 My Profile")],
           [KeyboardButton("🕋 History"), KeyboardButton("📊 Price List")],
           [KeyboardButton("📞 Contact Support")]]
    if uid == ADMIN_ID:
        kb.append([KeyboardButton("⚙️ Admin Panel")])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def admin_menu():
    kb = [[KeyboardButton("➕ Add API"), KeyboardButton("📋 List APIs")],
           [KeyboardButton("➕ Add Product"), KeyboardButton("❌ Back")]]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    uname = update.effective_user.username or "User"
    db = get_db()
    c = db.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (uid, uname))
    db.commit()
    await update.message.reply_text(f"Welcome @{uname} to Little Moon Shop 🌙!", reply_markup=main_menu(uid))

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    
    if uid == ADMIN_ID and text == "⚙️ Admin Panel":
        await update.message.reply_text("⚙️ Admin Mode", reply_markup=admin_menu())
    elif text == "🛒 Buy Product":
        await update.message.reply_text("🛒 Coming soon...")
    elif text == "👤 My Profile":
        await update.message.reply_text("👤 Coming soon...")
    elif text == "🕋 History":
        await update.message.reply_text("🕋 Coming soon...")
    elif text == "📊 Price List":
        await update.message.reply_text("📊 Coming soon...")
    elif text == "📞 Contact Support":
        await update.message.reply_text("📞 Contact: @blessiq")
    elif text == "❌ Back" and uid == ADMIN_ID:
        await update.message.reply_text("Back to Main Menu", reply_markup=main_menu(uid))
    else:
        await update.message.reply_text("Please use menu buttons.", reply_markup=main_menu(uid))

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🚀 Bot is running on Render...")
    app.run_polling()

if __name__ == '__main__':
    main()
