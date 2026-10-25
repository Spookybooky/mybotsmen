import os
import sqlite3
import time
import threading
import random
import json
from datetime import datetime

import telebot
from telebot import types
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
admin_ids_str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(i.strip()) for i in admin_ids_str.split(",") if i.strip().isdigit()]

if not TOKEN or not ADMIN_IDS:
    raise SystemExit("Ошибка: Проверьте BOT_TOKEN и ADMIN_IDS в .env")

bot = telebot.TeleBot(TOKEN)
DB = "bot.db"

# Временное хранилище для создания рассылок
temp_broadcasts = {}

# ---------- БАЗА ДАННЫХ ----------
def db_init():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, 
        roblox_link TEXT, submitted_at INTEGER, access_at INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS broadcasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT, photo_id TEXT, 
        markup TEXT, interval_sec INTEGER, next_send INTEGER)""")
    
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (
        "welcome_text",
        "👋 Привет! Это бот для получения доступа к голосовому чату.\n\n"
        "Нажми на кнопку ниже, чтобы подать заявку."
    ))
    conn.commit()
    conn.close()

def get_setting(key):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def set_setting(key, value):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def save_user_link(user_id, username, first_name, link):
    now = int(time.time())
    access_at = now + 24 * 3600  # 24 часа
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""INSERT INTO users (user_id, username, first_name, roblox_link, submitted_at, access_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
        username=excluded.username, first_name=excluded.first_name, roblox_link=excluded.roblox_link,
        submitted_at=excluded.submitted_at, access_at=excluded.access_at""", 
        (user_id, username, first_name, link, now, access_at))
    conn.commit()
    conn.close()
    return access_at

def get_user(user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

# ---------- КЛАВИАТУРЫ ----------
def main_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("👤 Профиль", callback_data="profile"),
        types.InlineKeyboardButton("🎙 Получить войс-чат", callback_data="get_link"),
    )
    return kb

def admin_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("✏️ Изменить приветствие", callback_data="admin_edit_welcome"),
        types.InlineKeyboardButton("📋 Сданные заявки", callback_data="admin_links"),
        types.InlineKeyboardButton("📢 Создать рассылку", callback_data="admin_create_broadcast"),
        types.InlineKeyboardButton("🗑 Удалить рассылку", callback_data="admin_delete_broadcast"),
        types.InlineKeyboardButton("📊 Активные рассылки", callback_data="admin_list_broadcasts")
    )
    return kb

# ---------- ХЕНДЛЕРЫ ----------
@bot.message_handler(commands=['start'])
def cmd_start(message):
    welcome = get_setting("welcome_text")
    bot.send_message(message.chat.id, welcome, reply_markup=main_keyboard())

@bot.message_handler(commands=['admin'])
def cmd_admin(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "⛔ У вас нет доступа.")
        return
    bot.send_message(message.chat.id, "🛠 Админ-панель:", reply_markup=admin_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == "profile")
def cb_profile(call):
    u = get_user(call.from_user.id)
    if not u or not u[3]:
        status = "❌ <b>Войс-чат не подключен</b>"
    elif int(time.time()) < u[5]:
        status = "⏳ <b>В процессе получения</b>"
    else:
        status = "✅ <b>Войс-чат получен</b>"
        
    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"ID: <code>{call.from_user.id}</code>\n"
        f"Имя: {call.from_user.first_name}\n"
        f"Username: @{call.from_user.username or '—'}\n\n"
        f"Статус: {status}"
    )
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, text, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "get_link")
def cb_get_link(call):
    bot.answer_callback_query(call.id)
    u = get_user(call.from_user.id)
    if u and u[3]:
        left = u[5] - int(time.time())
        if left > 0:
            bot.send_message(call.message.chat.id, f"⏳ Вы уже подали заявку. Ждите: {left//3600} ч {(left%3600)//60} мин.")
        else:
            bot.send_message(call.message.chat.id, "✅ Ваша заявка обработана. Войс-чат получен!")
        return

    text = (
        "🔗 Отправьте ссылку на ваш профиль Roblox.\n\n"
        "ЧТО ПОНАДОБИТСЯ:\n"
        "· Браузер Firefox\n"
        "· Аккаунт Roblox с выполненным входом\n"
        "· Расширение Cookie-Editor\n"
        "· Telegram-бот, который принимает ваш токен\n\n"
        "ШАГ 1. УСТАНОВИТЬ FIREFOX И РАСШИРЕНИЕ\n"
        "1. Скачайте и установите Mozilla Firefox.\n"
        "2. Откройте браузер и в адресной строке введите: расширение cookie editor.\n"
        "3. Перейдите на сайт addons.mozilla.org — это официальный магазин дополнений Firefox.\n"
        "4. Найдите расширение Cookie-Editor и нажмите 'Добавить в Firefox'.\n"
        "5. Подтвердите установку.\n\n"
        "ШАГ 2. ВОЙТИ В ROBLOX\n"
        "1. Откройте сайт roblox.com.\n"
        "2. Если вход не выполнен — войдите в свой аккаунт.\n"
        "3. Убедитесь, что вы на нужной странице (главная или профиль).\n\n"
        "ШАГ 3. ОТКРЫТЬ COOKIE-EDITOR\n"
        "1. В правом верхнем углу Firefox нажмите на иконку из трёх горизонтальных линий (меню).\n"
        "2. В выпадающем списке выберите 'Расширения' (или 'Расширения и темы').\n"
        "3. Найдите в списке Cookie-Editor и нажмите на него.\n"
        "4. Откроется панель расширения со списком cookie для текущей вкладки.\n\n"
        "ШАГ 4. СКОПИРОВАТЬ НУЖНЫЙ COOKIE\n"
        "В списке найдите строку с именем .ROBLOSECURITY.\n"
        "1. Нажмите на эту строку, чтобы раскрыть значение.\n"
        "2. Скопируйте всё значение целиком.\n"
        "3. Не перепутайте с другими токенами — нужен именно .ROBLOSECURITY.\n\n"
        "ШАГ 5. ОТПРАВИТЬ БОТУ И ПОДОЖДАТЬ\n"
        "1. Откройте Telegram-бота.\n"
        "2. Отправьте скопированное значение токен сообщением.\n"
        "3. Дождитесь подтверждения от бота.\n"
        "4. Подождите 24 часа — это время обработки."
    )
    msg = bot.send_message(call.message.chat.id, text)
    bot.register_next_step_handler(msg, process_link)

def process_link(message):
    link = message.text.strip()
    
    # Проверка убрана — бот принимает любой текст
    access_at = save_user_link(message.from_user.id, message.from_user.username, message.from_user.first_name, link)
    access_str = datetime.fromtimestamp(access_at).strftime("%d.%m.%Y %H:%M")
    bot.reply_to(message, f"✅ Заявка принята!\n⏳ Ждите 24 часа. Доступ откроется: <b>{access_str}</b>", parse_mode="HTML")
    
    for admin in ADMIN_IDS:
        try:
            bot.send_message(admin, f"📥 Новая заявка!\nID: <code>{message.from_user.id}</code>\nДанные: {link}", parse_mode="HTML")
        except: pass

# ---------- РАССЫЛКИ И АДМИНКА ----------
@bot.callback_query_handler(func=lambda call: call.from_user.id in ADMIN_IDS and call.data.startswith("admin_"))
def cb_admin(call):
    bot.answer_callback_query(call.id)
    if call.data == "admin_edit_welcome":
        msg = bot.send_message(call.message.chat.id, "✏️ Пришлите новый текст приветствия:")
        bot.register_next_step_handler(msg, lambda m: set_setting("welcome_text", m.text) or bot.reply_to(m, "✅ Сохранено!"))
    
    elif call.data == "admin_links":
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("SELECT user_id, roblox_link FROM users WHERE roblox_link IS NOT NULL")
        rows = c.fetchall()
        conn.close()
        if not rows: bot.send_message(call.message.chat.id, "📭 Заявок нет.")
        else:
            text = "📋 <b>Сданные ссылки</b>\n\n"
            for r in rows[:20]: text += f"ID {r[0]}: {r[1]}\n"
            bot.send_message(call.message.chat.id, text, parse_mode="HTML", disable_web_page_preview=True)
            
    elif call.data == "admin_create_broadcast":
        msg = bot.send_message(call.message.chat.id, "Отправьте мне сообщение (текст/фото/с кнопками), которое будет рассылаться.")
        bot.register_next_step_handler(msg, process_broadcast_content)
        
    elif call.data == "admin_delete_broadcast":
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("SELECT id, text FROM broadcasts")
        rows = c.fetchall()
        conn.close()
        if not rows: bot.send_message(call.message.chat.id, "Нет активных рассылок.")
        else:
            kb = types.InlineKeyboardMarkup(row_width=1)
            for r in rows: kb.add(types.InlineKeyboardButton(f"Удалить №{r[0]}", callback_data=f"del_bc_{r[0]}"))
            bot.send_message(call.message.chat.id, "Выберите рассылку для удаления:", reply_markup=kb)
            
    elif call.data == "admin_list_broadcasts":
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("SELECT id, text, interval_sec FROM broadcasts")
        rows = c.fetchall()
        conn.close()
        if not rows: bot.send_message(call.message.chat.id, "Нет активных рассылок.")
        else:
            text = "📊 <b>Активные рассылки</b>\n\n"
            for r in rows: text += f"№{r[0]}: {r[1][:20]}... (каждые {r[2]//60} мин)\n"
            bot.send_message(call.message.chat.id, text, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("del_bc_"))
def cb_del_broadcast(call):
    bc_id = int(call.data.split("_")[2])
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("DELETE FROM broadcasts WHERE id = ?", (bc_id,))
    conn.commit()
    conn.close()
    bot.edit_message_text(f"✅ Рассылка №{bc_id} удалена.", call.message.chat.id, call.message.message_id)

def process_broadcast_content(message):
    temp_id = str(int(time.time()))
    
    text = message.text or message.caption or ""
    photo_id = message.photo[-1].file_id if message.photo else None
    markup_json = None
    if message.reply_markup:
        markup_json = json.dumps(message.reply_markup.to_dict())
        
    temp_broadcasts[temp_id] = {
        "text": text,
        "photo_id": photo_id,
        "markup": markup_json
    }
        
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("2 мин", callback_data=f"setbc_2m_{temp_id}"),
        types.InlineKeyboardButton("2 часа", callback_data=f"setbc_2h_{temp_id}"),
        types.InlineKeyboardButton("3 часа", callback_data=f"setbc_3h_{temp_id}"),
        types.InlineKeyboardButton("5 часов", callback_data=f"setbc_5h_{temp_id}")
    )
    bot.reply_to(message, "Выберите интервал рассылки:", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("setbc_"))
def cb_set_interval(call):
    parts = call.data.split("_")
    interval_code = parts[1]
    temp_id = parts[2]
    
    if temp_id not in temp_broadcasts:
        bot.answer_callback_query(call.id, "❌ Ошибка: данные устарели, создайте рассылку заново.", show_alert=True)
        return
        
    data = temp_broadcasts.pop(temp_id)
    text = data["text"]
    photo_id = data["photo_id"]
    markup_json = data["markup"]
    
    intervals = {"2m": 120, "2h": 7200, "3h": 10800, "5h": 18000}
    interval_sec = intervals.get(interval_code, 7200)
    
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT INTO broadcasts (text, photo_id, markup, interval_sec, next_send) VALUES (?, ?, ?, ?, ?)",
              (text, photo_id, markup_json, interval_sec, int(time.time()) + interval_sec))
    conn.commit()
    bc_id = c.lastrowid
    conn.close()
    
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        f"✅ Рассылка №{bc_id} создана! Будет отправляться каждые {interval_sec//60} мин.", 
        call.message.chat.id, 
        call.message.message_id
    )

# ---------- ФОНОВЫЕ ЗАДАЧИ ----------
def background_worker():
    while True:
        try:
            now = int(time.time())
            conn = sqlite3.connect(DB)
            c = conn.cursor()
            
            # 1. Проверка 24 часов для доступа
            c.execute("SELECT user_id FROM users WHERE access_at IS NOT NULL AND access_at <= ?", (now,))
            for (uid,) in c.fetchall():
                try: bot.send_message(uid, "✅ 24 часа прошли. Ваш войс-чат получен!")
                except: pass
                c.execute("UPDATE users SET access_at = NULL WHERE user_id = ?", (uid,))
            
            # 2. Проверка рассылок
            c.execute("SELECT id, text, photo_id, markup, next_send, interval_sec FROM broadcasts WHERE next_send <= ?", (now,))
            bcs = c.fetchall()
            if bcs:
                bc = random.choice(bcs)
                bc_id, text, photo_id, markup_json, next_send, interval = bc
                
                c.execute("SELECT user_id FROM users")
                users = [u[0] for u in c.fetchall()]
                print(f"[РАССЫЛКА №{bc_id}] Начинаю отправку {len(users)} пользователям...")
                
                markup = None
                if markup_json:
                    try:
                        data = json.loads(markup_json)
                        markup = types.InlineKeyboardMarkup(row_width=data.get("row_width", 3))
                        for row in data.get("inline_keyboard", []):
                            buttons = []
                            for btn in row:
                                buttons.append(types.InlineKeyboardButton(
                                    text=btn.get("text", "Кнопка"), 
                                    url=btn.get("url"), 
                                    callback_data=btn.get("callback_data")
                                ))
                            markup.add(*buttons)
                    except Exception as e:
                        print(f"Ошибка загрузки кнопок: {e}")

                success_count = 0
                for uid in users:
                    try:
                        if photo_id:
                            bot.send_photo(uid, photo_id, caption=text, reply_markup=markup, parse_mode="HTML")
                        else:
                            bot.send_message(uid, text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)
                        success_count += 1
                    except Exception as e:
                        print(f"Не удалось отправить {uid}: {e}")
                
                print(f"[РАССЫЛКА №{bc_id}] Успешно отправлено: {success_count} из {len(users)}")
                c.execute("UPDATE broadcasts SET next_send = ? WHERE id = ?", (now + interval, bc_id))

            conn.commit()
            conn.close()
        except Exception as e:
            print("Worker error:", e)
        time.sleep(30)

if __name__ == "__main__":
    db_init()
    threading.Thread(target=background_worker, daemon=True).start()
    print("Бот запущен...")
    bot.infinity_polling()