import os
import sqlite3
import logging
import random
import string
import json
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None

# Shweboost.com API Configuration
API_KEY = "9ac05a01dd452421ef21588c6e1accdc"
API_URL = "https://shweboost.com/api/v2"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def mm_time():
    return datetime.now(timezone(timedelta(hours=6, minutes=30)))

LVL_EMOJI = {'Normal': '🥉 Member', 'Silver': '🥈 Silver VIP', 'Gold': '🥇 Gold VIP'}

def init_db():
    conn = sqlite3.connect('littlemoon_pro.db', check_same_thread=False, timeout=15.0)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance REAL, level TEXT, is_banned INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS categories (name TEXT PRIMARY KEY)")
    c.execute("CREATE TABLE IF NOT EXISTS products (shortcode TEXT PRIMARY KEY, category TEXT, name TEXT, n_price REAL, s_price REAL, g_price REAL, service_id INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT, amount REAL, detail TEXT, date TEXT)")
    conn.commit()
    return conn

db = init_db()

U_AMT, U_SS = range(2)
A_CAT, A_ITEM_CAT, A_ITEM_NAME, A_ITEM_SC, A_ITEM_PRICE, A_ITEM_SERVICE = range(2, 8)

def get_user(uid, uname="User"):
    c = db.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    user = c.fetchone()
    if not user:
        c.execute("INSERT INTO users VALUES (?, ?, 0, 'Normal', 0)", (uid, uname))
        db.commit()
        return (uid, uname, 0, 'Normal', 0)
    if user[1] != uname:
        c.execute("UPDATE users SET username=? WHERE user_id=?", (uname, uid))
        db.commit()
    return user

def build_history_text(h):
    date_str = str(h[4])
    date_part = date_str[:10] if len(date_str) >= 10 else date_str
    time_part = date_str[11:19] if len(date_str) >= 19 else "N/A"
    if h[1] == 'Buy':
        try:
            item, code = h[3].split('||')
        except:
            item, code = h[3], "N/A"
        return (f"🛒 <b>Buy Product</b>\nItem: {item}\nPrice: ${h[2]:,.0f}\nDate: {date_part} | {time_part}\nCode: <code>{code}</code>\n")
    elif h[1] == 'Add Fund':
        return (f"🏦 <b>Add Fund</b>\nAmt: ${h[2]:,.0f}\nTX ID: {h[3]}\nDate: {date_part} | {time_part}\n")
    elif h[1] == 'Minus Fund':
        return (f"📉 <b>Minus Fund</b>\nAmt: ${h[2]:,.0f}\nDate: {date_part} | {time_part}\n")
    return ""

def main_menu(uid):
    kb = [
        [KeyboardButton("🛒 Buy Product"), KeyboardButton("👤 My Profile")],
        [KeyboardButton("🕋 History"), KeyboardButton("📊 Price List")],
        [KeyboardButton("📢 Join Announcement GP"), KeyboardButton("🤝 Join Reseller Program")],
        [KeyboardButton("📞 Contact Support")]
    ]
    if uid == ADMIN_ID:
        kb.append([KeyboardButton("⚙️ Admin Panel")])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def admin_menu():
    kb = [
        [KeyboardButton("➕ New Category"), KeyboardButton("➕ New Item")],
        [KeyboardButton("👥 User List"), KeyboardButton("📊 User Stats")],
        [KeyboardButton("📈 Sale Report"), KeyboardButton("📦 Check Stock")],
        [KeyboardButton("💳 Check Wallet Hist"), KeyboardButton("🛒 Check Buy Hist")],
        [KeyboardButton("📜 Admin Commands"), KeyboardButton("❌ Cancel")]
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def cancel_menu():
    return ReplyKeyboardMarkup([[KeyboardButton("❌ Cancel")]], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    uname = update.effective_user.username or "User"
    user = get_user(uid, uname)
    if user[4] == 1: return
    await update.message.reply_text(f"Welcome @{uname} to Little Moon Shop 🌙!", reply_markup=main_menu(uid))

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text: return
    uid = update.effective_user.id
    uname = update.effective_user.username or "User"
    user = get_user(uid, uname)
    if user[4] == 1: return
    
    # API Order Flow - Waiting for Link
    if context.user_data.get('awaiting_api_link') and text != "❌ Cancel":
        context.user_data['api_link'] = text
        context.user_data['awaiting_api_link'] = False
        await update.message.reply_text("🔢 Enter quantity (number of likes/views/followers):")
        context.user_data['awaiting_api_qty'] = True
        return
    
    # API Order Flow - Waiting for Quantity
    if context.user_data.get('awaiting_api_qty'):
        try:
            qty = int(text)
        except:
            await update.message.reply_text("⚠️ Please enter a valid number.")
            return
        
        api_order = context.user_data.get('temp_api_order')
        if not api_order:
            return
        
        context.user_data['awaiting_api_qty'] = False
        
        payload = {
            "key": API_KEY,
            "action": "add",
            "service": api_order['service_id'],
            "link": context.user_data['api_link'],
            "quantity": qty
        }
        
        try:
            response = requests.post(API_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
            result = response.json()
            
            if "order" in result:
                c = db.cursor()
                c.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (api_order['price'], uid))
                now_str = mm_time().strftime("%Y-%m-%d %H:%M:%S")
                c.execute("INSERT INTO history (user_id, type, amount, detail, date) VALUES (?,?,?,?,?)",
                          (uid, 'Buy', api_order['price'], f"{api_order['p_name']}||Order ID: {result['order']}", now_str))
                db.commit()
                
                await update.message.reply_text(
                    f"✅ Order placed successfully via API!\n\n"
                    f"📦 Product: {api_order['p_name']}\n"
                    f"🔢 Quantity: {qty}\n"
                    f"💰 Amount: ${api_order['price']:,.0f}\n"
                    f"🆔 API Order ID: <code>{result['order']}</code>\n\n"
                    f"Your order will be processed automatically.",
                    parse_mode='HTML'
                )
                
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"🛒 New API Order!\nUser: {uid} (@{uname})\nProduct: {api_order['p_name']}\nQty: {qty}\nAmount: ${api_order['price']}\nAPI Order ID: {result['order']}",
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text(f"⚠️ API Error: {result.get('error', 'Unknown error')}")
        except Exception as e:
            await update.message.reply_text(f"⚠️ API Error: {str(e)[:100]}")
        
        context.user_data.pop('temp_api_order', None)
        context.user_data.pop('api_link', None)
        return
    
    c = db.cursor()
    if text == "👤 My Profile":
        lvl_str = LVL_EMOJI.get(user[3], '🥉 Member')
        txt = (f"👤 <b>My Wallet Profile</b>\n━━━━━━━━━━━━━━━\n🆔 <b>ID:</b> <code>{uid}</code>\n🎖 <b>Level:</b> {lvl_str}\n💰 <b>Balance:</b> ${user[2]:,.0f}\n━━━━━━━━━━━━━━━")
        kb = [[InlineKeyboardButton("➕ Add Fund", callback_data="btn_addfund")]]
        await update.message.reply_text(txt, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))
    elif text == "📊 Price List":
        c.execute("SELECT category, name, n_price, s_price, g_price FROM products ORDER BY category")
        prods = c.fetchall()
        if not prods:
            return await update.message.reply_text("⚠️ ဈေးနှုန်းစာရင်း မရှိသေးပါ။")
        msg = "📊 <b>Little Moon Price List</b>\n\n💡 <b>Member Tiers:</b>\n🥉 Normal Member Price\n🥈 Silver VIP Price\n🥇 Gold VIP Price\n\n"
        current_cat = ""
        for p in prods:
            if p[0] != current_cat:
                current_cat = p[0]
                msg += f"\n📁 <b>{current_cat}</b>\n"
            msg += f"▪️ {p[1]} ➔ 🥉 ${p[2]:.0f} | 🥈 ${p[3]:.0f} | 🥇 ${p[4]:.0f}\n"
        await update.message.reply_text(msg, parse_mode='HTML')
    elif text == "🕋 History":
        c.execute("SELECT id, type, amount, detail, date FROM history WHERE user_id=? ORDER BY id DESC", (uid,))
        hists = c.fetchall()
        if not hists:
            return await update.message.reply_text("⚠️ မှတ်တမ်း မရှိသေးပါ။")
        msg = "🕋 <b>သင့်လုပ်ဆောင်ချက် မှတ်တမ်းများ</b>\n━━━━━━━━━━━━━━━\n\n"
        for h in hists[:5]: msg += build_history_text(h) + "━━━━━━━━━━━━━━━\n"
        kb = []
        if len(hists) > 5:
            kb.append([InlineKeyboardButton("Next ➡️", callback_data="hist_u_1_all")])
        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb) if kb else None)
    elif text == "🛒 Buy Product":
        c.execute("SELECT name FROM categories")
        cats = c.fetchall()
        if not cats:
            return await update.message.reply_text("⚠️ ပစ္စည်းများ မရှိသေးပါ။")
        kb = [[InlineKeyboardButton(cat[0], callback_data=f"b_cat_{cat[0]}")] for cat in cats]
        await update.message.reply_text("🛒 ဝယ်ယူမည်ကို ရွေးချယ်ပါ-", reply_markup=InlineKeyboardMarkup(kb))
    elif text == "📢 Join Announcement GP":
        await update.message.reply_text("Join: https://t.me/+Ez8yyUbzZUM3ZTE1")
    elif text == "🤝 Join Reseller Program":
        await update.message.reply_text("🤝 Reseller Program ဝင်ရောက်ရန် Member ကြေး သတ်မှတ်ချက်များ ရှိပါသည်။\nအသေးစိတ် သိရှိရန် Admin ကို ဆက်သွယ်ပါဗျ။")
    elif text == "📞 Contact Support":
        await update.message.reply_text("Contact: @blessiq")
    elif text == "⚙️ Admin Panel" and uid == ADMIN_ID:
        await update.message.reply_text("⚙️ <b>Admin Mode Activated</b>\nအောက်ပါ Menu များကို အသုံးပြုပါ။", parse_mode='HTML', reply_markup=admin_menu())
    elif text == "❌ Cancel" and uid == ADMIN_ID:
        await update.message.reply_text("🏠 Admin Mode မှ ထွက်ပြီး Main Menu သို့ ပြန်ရောက်ပါပြီ။", reply_markup=main_menu(uid))
    elif text == "👥 User List" and uid == ADMIN_ID:
        c.execute("SELECT user_id, username, balance, level FROM users ORDER BY balance DESC LIMIT 20 OFFSET 0")
        users = c.fetchall()
        msg = "👥 <b>User List (Page 1)</b>\n━━━━━━━━━━━━━━━\n"
        for u in users:
            emo = LVL_EMOJI.get(u[3], '🥉').split()[0]
            msg += f"🆔 <code>{u[0]}</code> | {emo} @{u[1]} | 💰 ${u[2]:.0f}\n"
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        kb = []
        if total_users > 20:
            kb.append([InlineKeyboardButton("Next ➡️", callback_data="ulist_1")])
        await update.message.reply_text(msg if users else "⚠️ User မရှိသေးပါ။", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb) if kb else None)
    elif text == "📊 User Stats" and uid == ADMIN_ID:
        c.execute("SELECT COUNT(*), SUM(balance) FROM users")
        total_u, total_bal = c.fetchone()
        c.execute("SELECT level, COUNT(*) FROM users GROUP BY level")
        lvls = dict(c.fetchall())
        msg = (f"📊 <b>User Statistics</b>\n━━━━━━━━━━━━━━━\n👥 <b>Total Users:</b> {total_u}\n💰 <b>Total Balance:</b> ${total_bal or 0:,.0f}\n\n🥉 <b>Normal:</b> {lvls.get('Normal', 0)} ဦး\n🥈 <b>Silver:</b> {lvls.get('Silver', 0)} ဦး\n🥇 <b>Gold:</b> {lvls.get('Gold', 0)} ဦး")
        await update.message.reply_text(msg, parse_mode='HTML')
    elif text == "📈 Sale Report" and uid == ADMIN_ID:
        kb = [[InlineKeyboardButton("📊 Sale Summary", callback_data="rep_sum")], [InlineKeyboardButton("👥 User Sale Report", callback_data="rep_usr")]]
        await update.message.reply_text("📈 Report အမျိုးအစား ရွေးချယ်ပါ-", reply_markup=InlineKeyboardMarkup(kb))
    elif text == "📦 Check Stock" and uid == ADMIN_ID:
        c.execute("SELECT name FROM categories")
        cats = c.fetchall()
        if not cats: return await update.message.reply_text("⚠️ Category မရှိသေးပါ။")
        msg = "📦 <b>Product List (API Products - No Stock Needed)</b>\n━━━━━━━━━━━━━━━\n"
        for cat in cats:
            msg += f"📁 <b>{cat[0]}</b>\n"
            c.execute("SELECT name, shortcode FROM products WHERE category=?", (cat[0],))
            for p in c.fetchall():
                msg += f"  🔌 {p[0]} | <code>{p[1]}</code> : <b>API Product</b>\n"
            msg += "\n"
        await update.message.reply_text(msg, parse_mode='HTML')
    elif text == "💳 Check Wallet Hist" and uid == ADMIN_ID:
        await update.message.reply_text("🔍 <code>/whist [UserID]</code> ဟု ရိုက်ထည့်ပါ။", parse_mode='HTML')
    elif text == "🛒 Check Buy Hist" and uid == ADMIN_ID:
        await update.message.reply_text("🔍 <code>/bhist [UserID]</code> ဟု ရိုက်ထည့်ပါ။", parse_mode='HTML')
    elif text == "📜 Admin Commands" and uid == ADMIN_ID:
        guide = ("📜 <b>Admin Commands Guide</b>\n\n"
                 "💰 <b>Money:</b>\n<code>/wallet [ID] [Amt] [TXID]</code>\n<code>/minus [ID] [Amt]</code>\n\n"
                 "🎖 <b>Set Levels:</b>\n<code>/setnormal [ID]</code>\n<code>/setsilver [ID]</code>\n<code>/setgold [ID]</code>\n\n"
                 "🏷 <b>Set Prices:</b>\n<code>/np [code] price</code>\n<code>/sp [code] price</code>\n<code>/gp [code] price</code>\n\n"
                 "✏️ <b>Edit/Delete:</b>\n<code>/editcat OldName>NewName</code>\n<code>/edititem [shortcode] [New Name]</code>\n<code>/delitem [shortcode]</code>\n\n"
                 "🚫 <b>Ban System:</b>\n<code>/ban [ID]</code>\n<code>/unban [ID]</code>\n\n"
                 "📢 <b>Broadcast:</b>\n<code>/send [Message]</code>")
        await update.message.reply_text(guide, parse_mode='HTML')

async def dynamic_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    uid = update.effective_user.id
    await query.answer()
    c = db.cursor()
    
    if data.startswith("ulist_") and uid == ADMIN_ID:
        page = int(data.split("_")[1])
        offset = page * 20
        c.execute("SELECT user_id, username, balance, level FROM users ORDER BY balance DESC LIMIT 20 OFFSET ?", (offset,))
        users = c.fetchall()
        msg = f"👥 <b>User List (Page {page+1})</b>\n━━━━━━━━━━━━━━━\n"
        for u in users:
            emo = LVL_EMOJI.get(u[3], '🥉').split()[0]
            msg += f"🆔 <code>{u[0]}</code> | {emo} @{u[1]} | 💰 ${u[2]:.0f}\n"
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        kb = []
        row = []
        if page > 0:
            row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"ulist_{page-1}"))
        if offset + 20 < total_users:
            row.append(InlineKeyboardButton("Next ➡️", callback_data=f"ulist_{page+1}"))
        if row: kb.append(row)
        try:
            await query.edit_message_text(msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb) if kb else None)
        except: pass
        return
    
    c.execute("SELECT level, balance FROM users WHERE user_id=?", (uid,))
    usr = c.fetchone()
    if not usr: return
    lvl, bal = usr[0], usr[1]
    lvl_emoji = LVL_EMOJI.get(lvl, '🥉 Member')
    
    if data.startswith("b_cat_"):
        cat = data.split("_", 2)[2]
        c.execute("SELECT name, shortcode, n_price, s_price, g_price FROM products WHERE category=?", (cat,))
        kb = []
        for p in c.fetchall():
            my_price = p[2] if lvl == 'Normal' else (p[3] if lvl == 'Silver' else p[4])
            kb.append([InlineKeyboardButton(f"🔌 {p[0]} | ${my_price:,.0f} | API", callback_data=f"b_item_{p[1]}")])
        kb.append([InlineKeyboardButton("⬅️ Back", callback_data="b_back")])
        try:
            await query.edit_message_text(f"🛒 <b>{cat}</b> ဝယ်ယူရန် ရွေးချယ်ပါ\n(Your Tier: {lvl_emoji})", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))
        except: pass
    elif data == "b_back":
        c.execute("SELECT name FROM categories")
        kb = [[InlineKeyboardButton(cat[0], callback_data=f"b_cat_{cat[0]}")] for cat in c.fetchall()]
        try:
            await query.edit_message_text("🛒 ဝယ်ယူမည်ကို ရွေးချယ်ပါ-", reply_markup=InlineKeyboardMarkup(kb))
        except: pass
    elif data.startswith("b_item_"):
        sc = data.split("_", 2)[2]
        c.execute("SELECT name, n_price, s_price, g_price, service_id FROM products WHERE shortcode=?", (sc,))
        prod = c.fetchone()
        my_price = prod[1] if lvl == 'Normal' else (prod[2] if lvl == 'Silver' else prod[3])
        
        txt = (f"🛒 <b>Confirm API Order</b>\n━━━━━━━━━━━━━━━\n"
               f"🎁 <b>Item:</b> {prod[0]}\n"
               f"🎖 <b>Tier:</b> {lvl_emoji}\n"
               f"💵 <b>Price:</b> ${my_price:,.0f}\n"
               f"💰 <b>Your Balance:</b> ${bal:,.0f}\n"
               f"🔌 <b>Type:</b> API (Auto Delivery)\n━━━━━━━━━━━━━━━\nဝယ်ယူရန် သေချာပါသလား?")
        kb = [[InlineKeyboardButton("✅ Confirm API Order", callback_data=f"b_conf_{sc}_{my_price}")], [InlineKeyboardButton("❌ Cancel", callback_data="b_back")]]
        try:
            await query.edit_message_text(txt, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))
        except: pass
    elif data.startswith("b_conf_"):
        parts = data.split("_")
        sc, price = parts[2], float(parts[3])
        c.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        if c.fetchone()[0] < price:
            return await query.edit_message_text("⚠️ သင့်အကောင့်တွင် ငွေလုံလောက်မှု မရှိပါ။")
        
        c.execute("SELECT name, service_id FROM products WHERE shortcode=?", (sc,))
        prod = c.fetchone()
        if not prod:
            return await query.edit_message_text("⚠️ Product not found.")
        
        p_name, service_id = prod[0], prod[1]
        
        context.user_data['temp_api_order'] = {
            'service_id': service_id,
            'price': price,
            'p_name': p_name
        }
        await query.edit_message_text(f"🎁 Product: {p_name}\n💵 Price: ${price:,.0f}\n\n📎 Please enter the TikTok video link or username:\n(Example: https://tiktok.com/@user/video/123 or @username)")
        context.user_data['awaiting_api_link'] = True
        return
    elif data.startswith("hist_"):
        parts = data.split("_")
        target = parts[1]
        page = int(parts[2])
        htype = parts[3] if len(parts) > 3 else 'all'
        check_uid = uid if target == 'u' else int(target)
        if target != 'u':
            c.execute("SELECT level FROM users WHERE user_id=?", (check_uid,))
            res = c.fetchone()
            lvl_emo = LVL_EMOJI.get(res[0], '🥉').split()[0] if res else '🥉'
            title = f"Admin {'Wallet' if htype=='wallet' else 'Buy'} History for <code>{check_uid}</code> {lvl_emo}"
        else:
            title = "သင့်လုပ်ဆောင်ချက် မှတ်တမ်းများ"
        if htype == 'wallet': t_filter = "AND type IN ('Add Fund', 'Minus Fund')"
        elif htype == 'buy': t_filter = "AND type = 'Buy'"
        else: t_filter = ""
        c.execute(f"SELECT id, type, amount, detail, date FROM history WHERE user_id=? {t_filter} ORDER BY id DESC", (check_uid,))
        all_hists = c.fetchall()
        start_idx = page * 5
        end_idx = start_idx + 5
        page_hists = all_hists[start_idx:end_idx]
        msg = f"🕋 <b>{title} (Page {page+1})</b>\n━━━━━━━━━━━━━━━\n\n"
        for h in page_hists: msg += build_history_text(h) + "━━━━━━━━━━━━━━━\n"
        kb = []
        row = []
        if page > 0: row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"hist_{target}_{page-1}_{htype}"))
        if end_idx < len(all_hists): row.append(InlineKeyboardButton("Next ➡️", callback_data=f"hist_{target}_{page+1}_{htype}"))
        if row: kb.append(row)
        try:
            await query.edit_message_text(msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb) if kb else None)
        except: pass
    elif data == "rep_sum" and uid == ADMIN_ID:
        today = mm_time().strftime("%Y-%m-%d")
        c.execute("SELECT SUM(amount) FROM history WHERE type='Buy' AND date LIKE ?", (f"{today}%",))
        today_amt = c.fetchone()[0] or 0
        c.execute("SELECT SUM(amount) FROM history WHERE type='Buy'")
        total_amt = c.fetchone()[0] or 0
        c.execute("SELECT detail FROM history WHERE type='Buy' AND date LIKE ?", (f"{today}%",))
        t_items = {}
        for row in c.fetchall():
            item = row[0].split('||')[0] if '||' in row[0] else row[0]
            t_items[item] = t_items.get(item, 0) + 1
        c.execute("SELECT detail FROM history WHERE type='Buy'")
        all_items = {}
        for row in c.fetchall():
            item = row[0].split('||')[0] if '||' in row[0] else row[0]
            all_items[item] = all_items.get(item, 0) + 1
        today_best = max(t_items, key=t_items.get) if t_items else "None"
        all_best = max(all_items, key=all_items.get) if all_items else "None"
        msg = f"📊 <b>Sale Summary Report</b>\n━━━━━━━━━━━━━━━\n💵 <b>Today Sale:</b> ${today_amt:,.0f}\n💰 <b>Total Sale:</b> ${total_amt:,.0f}\n\n🔥 <b>Today Bestseller:</b> {today_best}\n🏆 <b>All-Time Bestseller:</b> {all_best}\n\n📅 <b>Today Items Sold:</b>\n"
        for k, v in t_items.items(): msg += f" - {k}: {v} ခု\n"
        if not t_items: msg += " - No sales today\n"
        msg += f"\n📦 <b>Total Items Sold:</b>\n"
        for k, v in all_items.items(): msg += f" - {k}: {v} ခု\n"
        kb = [[InlineKeyboardButton("⬅️ Back to Reports", callback_data="rep_back")]]
        try:
            await query.edit_message_text(msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))
        except: pass
    elif data == "rep_usr" and uid == ADMIN_ID:
        today = mm_time().strftime("%Y-%m-%d")
        month = mm_time().strftime("%Y-%m")
        month_name = mm_time().strftime("%B")
        msg = f"👥 <b>User Sale Report</b>\n━━━━━━━━━━━━━━━\n\n🌟 <b>Top 10 Bestsellers - {month_name}</b>\n"
        c.execute("""SELECT h.user_id, u.level, COUNT(h.id), SUM(h.amount) FROM history h JOIN users u ON h.user_id = u.user_id WHERE h.type='Buy' AND h.date LIKE ? GROUP BY h.user_id ORDER BY SUM(h.amount) DESC LIMIT 10""", (f"{month}%",))
        for r in c.fetchall():
            emo = LVL_EMOJI.get(r[1], '🥉').split()[0]
            msg += f"🆔 <code>{r[0]}</code> | {emo} | {r[2]} ကြိမ် | ${r[3]:,.0f}\n"
        msg += f"\n📅 <b>Today's Buyers</b>\n"
        c.execute("""SELECT h.user_id, u.level, COUNT(h.id), SUM(h.amount) FROM history h JOIN users u ON h.user_id = u.user_id WHERE h.type='Buy' AND h.date LIKE ? GROUP BY h.user_id ORDER BY SUM(h.amount) DESC""", (f"{today}%",))
        today_buyers = c.fetchall()
        for r in today_buyers:
            emo = LVL_EMOJI.get(r[1], '🥉').split()[0]
            msg += f"🆔 <code>{r[0]}</code> | {emo} | {r[2]} ကြိမ် | ${r[3]:,.0f}\n"
        if not today_buyers: msg += " - No buyers today\n"
        kb = [[InlineKeyboardButton("⬅️ Back to Reports", callback_data="rep_back")]]
        try:
            await query.edit_message_text(msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))
        except: pass
    elif data == "rep_back" and uid == ADMIN_ID:
        kb = [[InlineKeyboardButton("📊 Sale Summary", callback_data="rep_sum")], [InlineKeyboardButton("👥 User Sale Report", callback_data="rep_usr")]]
        try:
            await query.edit_message_text("📈 Report အမျိုးအစား ရွေးချယ်ပါ-", reply_markup=InlineKeyboardMarkup(kb))
        except: pass

async def fund_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await context.bot.send_message(query.message.chat_id, "💳 ဖြည့်မည့် ပမာဏကို ဂဏန်းသီးသန့် ရိုက်ထည့်ပါဗျာ။", reply_markup=cancel_menu())
    return U_AMT

async def fund_amt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text and text == "