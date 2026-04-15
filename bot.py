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
    if text and text == "❌ Cancel":
        await update.message.reply_text("❌ ငွေဖြည့်ခြင်း ပယ်ဖျက်လိုက်ပါပြီ။", reply_markup=main_menu(update.effective_user.id))
        return ConversationHandler.END
    if not text or not text.isdigit():
        await update.message.reply_text("⚠️ ဂဏန်းသီးသန့်သာ ရိုက်ပေးပါဗျ။", reply_markup=cancel_menu())
        return U_AMT
    context.user_data['amt'] = text
    msg = ("Payment (K pay, Wave, UAB, AYA)\n<code>09959937103</code> (May Lwin Oo)\nNote မှာ shop လို့ ရေးပေးပါ\n\nငွေလွှဲပီး ပြေစာ ပို့ပေးပါဗျ")
    await update.message.reply_text(msg, parse_mode='HTML', reply_markup=cancel_menu())
    return U_SS

async def fund_ss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text and text == "❌ Cancel":
        await update.message.reply_text("❌ ငွေဖြည့်ခြင်း ပယ်ဖျက်လိုက်ပါပြီ။", reply_markup=main_menu(update.effective_user.id))
        return ConversationHandler.END
    if not update.message.photo:
        await update.message.reply_text("⚠️ SS ပုံလေး ပို့ပေးပါဗျ။")
        return U_SS
    uid, uname = update.effective_user.id, update.effective_user.username or "User"
    amt = context.user_data['amt']
    txid = '#' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    await update.message.reply_text(f"✅ Add Fund Request Sent!\nAmt: ${amt}\nTXID: {txid}", reply_markup=main_menu(uid))
    c = db.cursor()
    c.execute("SELECT level FROM users WHERE user_id=?", (uid,))
    lvl = c.fetchone()[0]
    emo = LVL_EMOJI.get(lvl, '🥉 Member')
    admin_msg = f"🔔 <b>New Fund Request</b>\nUser: <code>{uid}</code> | @{uname}\nTier: {emo}\nAmt: ${amt}\n<code>/wallet {uid} {amt} {txid}</code>"
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=update.message.photo[-1].file_id, caption=admin_msg, parse_mode='HTML')
    return ConversationHandler.END

async def ap_add_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("📁 Category အမည် အသစ်ရိုက်ထည့်ပါ။ (ဥပမာ - TikTok Services)\nမလုပ်တော့ပါက ❌ Cancel နှိပ်ပါ။", reply_markup=cancel_menu())
    return A_CAT

async def ap_save_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text: return A_CAT
    if text == "❌ Cancel":
        await update.message.reply_text("Canceled.", reply_markup=admin_menu())
        return ConversationHandler.END
    try:
        db.cursor().execute("INSERT INTO categories VALUES (?)", (text,))
        db.commit()
        await update.message.reply_text(f"✅ Category '{text}' ဆောက်ပြီးပါပြီ။", reply_markup=admin_menu())
    except:
        await update.message.reply_text("⚠️ နာမည်တူ ရှိပြီးသားပါ။", reply_markup=admin_menu())
    return ConversationHandler.END

async def ap_add_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    c = db.cursor()
    c.execute("SELECT name FROM categories")
    cats = c.fetchall()
    if not cats:
        await update.message.reply_text("⚠️ Category အရင်ဆောက်ပါ။", reply_markup=admin_menu())
        return ConversationHandler.END
    kb = [[InlineKeyboardButton(c[0], callback_data=f"aci_{c[0]}")] for c in cats]
    await update.message.reply_text("👇 မည်သည့် Category အောက်တွင် ထည့်မည်နည်း?", reply_markup=InlineKeyboardMarkup(kb))
    return A_ITEM_CAT

async def ap_item_cat_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['a_cat'] = query.data.split("_")[1]
    await context.bot.send_message(query.message.chat_id, f"📁 {context.user_data['a_cat']} ရွေးချယ်ထားသည်။\n\nItem Name ရိုက်ထည့်ပါ (ဥပမာ - TikTok Likes 1000):", reply_markup=cancel_menu())
    return A_ITEM_NAME

async def ap_item_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text: return A_ITEM_NAME
    if text == "❌ Cancel":
        await update.message.reply_text("Canceled.", reply_markup=admin_menu())
        return ConversationHandler.END
    context.user_data['a_name'] = text
    await update.message.reply_text("Shortcode သတ်မှတ်ပါ (Space မပါရ၊ ဥပမာ - tt_likes_1000):")
    return A_ITEM_SC

async def ap_item_sc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text: return A_ITEM_SC
    if text == "❌ Cancel":
        await update.message.reply_text("Canceled.", reply_markup=admin_menu())
        return ConversationHandler.END
    context.user_data['a_sc'] = text
    await update.message.reply_text("ဈေးနှုန်း ၃ မျိုး Space ခြားရိုက်ပါ\n(Normal Silver Gold)\nဥပမာ - 4000 3000 2000")
    return A_ITEM_PRICE

async def ap_item_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text: return A_ITEM_PRICE
    if text == "❌ Cancel":
        await update.message.reply_text("Canceled.", reply_markup=admin_menu())
        return ConversationHandler.END
    try:
        p = text.split()
        n, s, g = float(p[0]), float(p[1]), float(p[2])
        context.user_data['a_n_price'] = n
        context.user_data['a_s_price'] = s
        context.user_data['a_g_price'] = g
        
        await update.message.reply_text(
            "🔢 Shweboost Service ID ထည့်ပါ။\n\n"
            "TikTok Likes → 491\n"
            "TikTok Views → 495\n"
            "TikTok Followers → 410\n\n"
            "ဥပမာ - 491"
        )
        return A_ITEM_SERVICE
    except:
        await update.message.reply_text("⚠️ Format မှားယွင်းနေပါသည်။ ဥပမာ - 4000 3000 2000", reply_markup=admin_menu())
        return ConversationHandler.END

async def ap_item_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text: return A_ITEM_SERVICE
    if text == "❌ Cancel":
        await update.message.reply_text("Canceled.", reply_markup=admin_menu())
        return ConversationHandler.END
    try:
        service_id = int(text)
        sc = context.user_data['a_sc']
        name = context.user_data['a_name']
        cat = context.user_data['a_cat']
        n = context.user_data['a_n_price']
        s = context.user_data['a_s_price']
        g = context.user_data['a_g_price']
        
        c = db.cursor()
        c.execute("INSERT INTO products (shortcode, category, name, n_price, s_price, g_price, service_id) VALUES (?,?,?,?,?,?,?)",
                  (sc, cat, name, n, s, g, service_id))
        db.commit()
        await update.message.reply_text(f"✅ API Product '{name}' ထည့်သွင်းပြီးပါပြီ။\n\nService ID: {service_id}\n\nUser များ ဝယ်ယူနိုင်ပါပြီ။", reply_markup=admin_menu())
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}", reply_markup=admin_menu())
    return ConversationHandler.END

async def admin_cmds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    text = update.message.text or update.message.caption
    if not text: return
    args = text.split()
    cmd = args[0].lower()
    c = db.cursor()
    now_str = mm_time().strftime("%Y-%m-%d %H:%M:%S")
    try:
        if cmd == "/send":
            msg_to_send = text.replace("/send", "", 1).strip()
            has_photo = bool(update.message.photo)
            photo_file_id = update.message.photo[-1].file_id if has_photo else None
            if not msg_to_send and not has_photo:
                return await update.message.reply_text("⚠️ ပို့မည့် စာ သို့မဟုတ် ပုံ ထည့်ပေးပါ။\nဥပမာ - /send Hello All")
            c.execute("SELECT user_id FROM users")
            users = c.fetchall()
            success, fail = 0, 0
            await update.message.reply_text("🚀 Broadcast စတင်နေပါပြီ... ခေတ္တစောင့်ပါ။")
            for u in users:
                try:
                    if has_photo:
                        await context.bot.send_photo(chat_id=u[0], photo=photo_file_id, caption=msg_to_send, parse_mode='HTML')
                    else:
                        await context.bot.send_message(chat_id=u[0], text=msg_to_send, parse_mode='HTML')
                    success += 1
                except:
                    fail += 1
            await update.message.reply_text(f"✅ Broadcast ပြီးဆုံးပါပြီ။\nအောင်မြင်: {success} ဦး\nမအောင်မြင်: {fail} ဦး")
            return
        if cmd == "/wallet" and len(args) == 4:
            uid, amt, txid = int(args[1]), float(args[2]), args[3]
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amt, uid))
            c.execute("INSERT INTO history (user_id, type, amount, detail, date) VALUES (?,?,?,?,?)", (uid, 'Add Fund', amt, txid, now_str))
            db.commit()
            c.execute("SELECT balance, level FROM users WHERE user_id=?", (uid,))
            res = c.fetchone()
            new_bal, lvl = res[0], res[1]
            emo = LVL_EMOJI.get(lvl, '🥉').split()[0]
            await update.message.reply_text(f"✅ <b>Fund Added</b>\nID: <code>{uid}</code> | {emo}\nAmt: +${amt}\nBal: ${new_bal:,.0f}", parse_mode='HTML')
            await context.bot.send_message(uid, f"🎉 ငွေဖြည့်သွင်းမှု အောင်မြင်ပါသည်!\nပမာဏ: ${amt:,.0f}\nလက်ကျန်ငွေ: ${new_bal:,.0f}", parse_mode='HTML')
        elif cmd == "/minus" and len(args) == 3:
            uid, amt = int(args[1]), float(args[2])
            c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amt, uid))
            c.execute("INSERT INTO history (user_id, type, amount, detail, date) VALUES (?,?,?,?,?)", (uid, 'Minus Fund', amt, 'Admin Deducted', now_str))
            db.commit()
            c.execute("SELECT balance, level FROM users WHERE user_id=?", (uid,))
            res = c.fetchone()
            new_bal, lvl = res[0], res[1]
            emo = LVL_EMOJI.get(lvl, '🥉').split()[0]
            await update.message.reply_text(f"✅ <b>Minus Success</b>\nID: <code>{uid}</code> | {emo}\nAmt: -${amt}\nBal: ${new_bal:,.0f}", parse_mode='HTML')
            await context.bot.send_message(uid, f"⚠️ သင့်အကောင့်မှ ငွေ ${amt:,.0f} နှုတ်ယူသွားပါသည်။\nလက်ကျန်ငွေ: ${new_bal:,.0f}", parse_mode='HTML')
        elif cmd == "/ban" and len(args) == 2:
            uid = int(args[1])
            c.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (uid,))
            db.commit()
            await update.message.reply_text(f"🚫 User {uid} ကို Ban လိုက်ပါပြီ။")
        elif cmd == "/unban" and len(args) == 2:
            uid = int(args[1])
            c.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (uid,))
            db.commit()
            await update.message.reply_text(f"✅ User {uid} ကို Unban လိုက်ပါပြီ။")
        elif cmd in ["/setnormal", "/setsilver", "/setgold"] and len(args) == 2:
            uid = int(args[1])
            level = cmd.replace('/set', '').capitalize()
            c.execute("UPDATE users SET level = ? WHERE user_id = ?", (level, uid))
            db.commit()
            emoji = LVL_EMOJI[level]
            await update.message.reply_text(f"✅ User <code>{uid}</code> is now {emoji}.", parse_mode='HTML')
            await context.bot.send_message(uid, f"🎉 သင့်အကောင့်ကို Admin မှ {emoji} အဖြစ် သတ်မှတ်လိုက်ပါသည်။", parse_mode='HTML')
        elif cmd in ["/np", "/sp", "/gp"] and len(args) == 3:
            sc, price = args[1], float(args[2])
            col = "n_price" if cmd == "/np" else ("s_price" if cmd == "/sp" else "g_price")
            c.execute(f"UPDATE products SET {col}=? WHERE shortcode=?", (price, sc))
            db.commit()
            await update.message.reply_text(f"✅ <code>{sc}</code> ၏ ဈေးနှုန်းအား ${price} သို့ ပြင်ဆင်ပြီးပါပြီ။", parse_mode='HTML')
        elif cmd == "/editcat" and len(args) >= 2:
            old_cat, new_cat = text.split(' ', 1)[1].split('>')
            old_cat, new_cat = old_cat.strip(), new_cat.strip()
            c.execute("UPDATE categories SET name=? WHERE name=?", (new_cat, old_cat))
            c.execute("UPDATE products SET category=? WHERE category=?", (new_cat, old_cat))
            db.commit()
            await update.message.reply_text(f"✅ '{old_cat}' မှ '{new_cat}' သို့ ပြောင်းလဲပြီးပါပြီ။")
        elif cmd == "/edititem" and len(args) >= 3:
            parts = text.split(maxsplit=2)
            sc, new_name = parts[1], parts[2]
            c.execute("UPDATE products SET name=? WHERE shortcode=?", (new_name, sc))
            db.commit()
            await update.message.reply_text(f"✅ Item <code>{sc}</code> အမည်ကို '{new_name}' သို့ ပြောင်းလဲပြီးပါပြီ။", parse_mode='HTML')
        elif cmd == "/delitem" and len(args) == 2:
            sc = args[1]
            c.execute("DELETE FROM products WHERE shortcode=?", (sc,))
            db.commit()
            await update.message.reply_text(f"🗑 Item <code>{sc}</code> အား ဖျက်လိုက်ပါပြီ။", parse_mode='HTML')
        elif cmd in ["/whist", "/bhist"] and len(args) == 2:
            uid = int(args[1])
            htype = 'wallet' if cmd == '/whist' else 'buy'
            t_filter = "IN ('Add Fund', 'Minus Fund')" if cmd == "/whist" else "='Buy'"
            c.execute(f"SELECT id, type, amount, detail, date FROM history WHERE user_id=? AND type {t_filter} ORDER BY id DESC", (uid,))
            hists = c.fetchall()
            if not hists: return await update.message.reply_text("⚠️ မှတ်တမ်း မရှိပါ။")
            c.execute("SELECT level FROM users WHERE user_id=?", (uid,))
            res = c.fetchone()
            lvl_emo = LVL_EMOJI.get(res[0], '🥉').split()[0] if res else '🥉'
            msg = f"🕋 <b>Admin {'Wallet' if cmd=='/whist' else 'Buy'} History for <code>{uid}</code> {lvl_emo} (Page 1)</b>\n━━━━━━━━━━━━━━━\n\n"
            for h in hists[:5]: msg += build_history_text(h) + "━━━━━━━━━━━━━━━\n"
            kb = []
            if len(hists) > 5: kb.append([InlineKeyboardButton("Next ➡️", callback_data=f"hist_{uid}_1_{htype}")])
            await update.message.reply_text(msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb) if kb else None)
    except Exception as e:
        logger.error(f"Admin CMD Error: {e}")
        await update.message.reply_text("⚠️ Command Format မှားယွင်းနေပါသည်။")

async def error_h(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error("System Error:", exc_info=context.error)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    fund_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(fund_start, pattern="^btn_addfund$")],
        states={U_AMT: [MessageHandler(filters.TEXT, fund_amt)], U_SS: [MessageHandler(filters.PHOTO | filters.TEXT, fund_ss)]},
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancel$"), fund_amt)]
    )
    
    admin_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^➕ New Category$"), ap_add_cat),
            MessageHandler(filters.Regex("^➕ New Item$"), ap_add_item)
        ],
        states={
            A_CAT: [MessageHandler(filters.TEXT, ap_save_cat)],
            A_ITEM_CAT: [CallbackQueryHandler(ap_item_cat_cb, pattern="^aci_")],
            A_ITEM_NAME: [MessageHandler(filters.TEXT, ap_item_name)],
            A_ITEM_SC: [MessageHandler(filters.TEXT, ap_item_sc)],
            A_ITEM_PRICE: [MessageHandler(filters.TEXT, ap_item_price)],
            A_ITEM_SERVICE: [MessageHandler(filters.TEXT, ap_item_service)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancel$"), ap_save_cat)]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(fund_conv)
    app.add_handler(admin_conv)
    app.add_handler(CallbackQueryHandler(dynamic_callbacks, pattern="^(b_|hist_|rep_|ulist_)"))
    app.add_handler(MessageHandler(filters.COMMAND | (filters.PHOTO & filters.CaptionRegex(r'^/')), admin_cmds))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_error_handler(error_h)
    
    print("🚀 Little Moon Shop PRO with Shweboost API is Running...")
    app.run_polling()

if __name__ == '__main__':
    main()