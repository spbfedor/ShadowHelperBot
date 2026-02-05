import os

import telebot
import sqlite3
import hashlib

from dotenv import load_dotenv
from telebot import types

load_dotenv()

# КОНФИГУРАЦИЯ
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_GROUP_ID = os.getenv("ADMIN_GROUP_ID")
DB_NAME = os.getenv("DB_NAME", "database.db")

bot = telebot.TeleBot(BOT_TOKEN)

# ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        # Связи сообщений (для ответов волонтеров)
        cursor.execute('CREATE TABLE IF NOT EXISTS message_links (group_msg_id INTEGER PRIMARY KEY, user_id INTEGER)')
        # Состояния квиза
        cursor.execute('CREATE TABLE IF NOT EXISTS user_states (user_id INTEGER PRIMARY KEY, step TEXT)')
        # Данные анкеты
        cursor.execute('''CREATE TABLE IF NOT EXISTS anketa_data 
                          (user_id INTEGER PRIMARY KEY, name TEXT, problem TEXT, age TEXT, urgency TEXT, format TEXT)''')
        conn.commit()

# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ 
def set_state(user_id, step):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('INSERT OR REPLACE INTO user_states VALUES (?, ?)', (user_id, step))

def get_state(user_id):
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.execute('SELECT step FROM user_states WHERE user_id = ?', (user_id,)).fetchone()
        return res[0] if res else None

def update_anketa(user_id, column, value):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute(f'INSERT OR IGNORE INTO anketa_data (user_id) VALUES (?)', (user_id,))
        conn.execute(f'UPDATE anketa_data SET {column} = ? WHERE user_id = ?', (value, user_id))

def get_user_alias(user_id):
    return "#" + hashlib.md5(str(user_id).encode()).hexdigest()[:5]

def save_link(group_msg_id, user_id):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('INSERT OR REPLACE INTO message_links VALUES (?, ?)', (group_msg_id, user_id))

def get_user_id_from_link(group_msg_id):
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.execute('SELECT user_id FROM message_links WHERE group_msg_id = ?', (group_msg_id,)).fetchone()
        return res[0] if res else None

# ЛОГИКА КВИЗА (АНКЕТЫ)
@bot.message_handler(commands=['start'])
def start_quiz(message):
    set_state(message.chat.id, 'START')
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Вперед! 🚀", callback_data="quiz_1"))
    
    text = ("Привет👋 Мы готовы тебя слушать. Чтобы помощь была быстрой и точной, "
            "пожалуйста, заполни короткую анкету. Это поможет нам подобрать волонтера.")
    bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('quiz_'))
def quiz_steps(call):
    user_id = call.message.chat.id
    
    # 1. ОБЯЗАТЕЛЬНО: отвечаем ТГ, что получили нажатие (убирает часики)
    bot.answer_callback_query(call.id)

    # ШАГ 1: Начало квиза -> Вопрос про имя
    if call.data == "quiz_1":
        set_state(user_id, "WAIT_NAME")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Оставить в секрете 🤐", callback_data="quiz_name_secret"))
        bot.edit_message_text("1. Как к тебе обращаться? (Напиши имя или нажми кнопку)", 
                              user_id, call.message.message_id, reply_markup=markup)

    # ШАГ 2: Кнопка "В секрете"
    elif call.data == "quiz_name_secret":
        update_anketa(user_id, "name", "Держит в секрете 🤐")
        set_state(user_id, "WAIT_PROBLEM")
        bot.edit_message_text("Понял, секретность — это важно.\n\n2. Какая основная причина обращения? Напиши кратко или укажи хэштегом (например, #тревога или #буллинг).", 
                              user_id, call.message.message_id, reply_markup=None)

    # ШАГ 3: Выбор возраста
    elif "quiz_age_" in call.data:
        age = "10-17" if "1017" in call.data else "18-30"
        update_anketa(user_id, "age", age)
        set_state(user_id, "WAIT_URGENCY")
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("Срочная поддержка сейчас", callback_data="quiz_urg_1"),
            types.InlineKeyboardButton("Готов(а) к долгому разговору", callback_data="quiz_urg_2"),
            types.InlineKeyboardButton("Хочу выговориться", callback_data="quiz_urg_3"),
            types.InlineKeyboardButton("Просто плохо, нужно разобраться", callback_data="quiz_urg_4")
        )
        bot.edit_message_text("4. Что тебе нужно прямо сейчас?", user_id, call.message.message_id, reply_markup=markup)

    # ШАГ 4: Срочность
    elif "quiz_urg_" in call.data:
        urg_map = {"1": "Срочно", "2": "Долгий разговор", "3": "Выговориться", "4": "Нужна помощь"}
        choice = call.data.split('_')[-1]
        update_anketa(user_id, "urgency", urg_map.get(choice, "Не указано"))
        set_state(user_id, "WAIT_FORMAT")
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("Только текстом", callback_data="quiz_form_1"),
            types.InlineKeyboardButton("Голосовыми сообщениями", callback_data="quiz_form_2"),
            types.InlineKeyboardButton("Без разницы", callback_data="quiz_form_3")
        )
        bot.edit_message_text("5. Как тебе удобнее общаться?", user_id, call.message.message_id, reply_markup=markup)

    # ШАГ 5: Формат общения (Финал)
    elif "quiz_form_" in call.data:
        form_map = {"1": "Текст", "2": "Голос", "3": "Без разницы"}
        choice = call.data.split('_')[-1]
        update_anketa(user_id, "format", form_map.get(choice, "Без разницы"))
        finish_quiz(call.message)

def finish_quiz(message):
    user_id = message.chat.id
    set_state(user_id, "COMPLETED")
    
    with sqlite3.connect(DB_NAME) as conn:
        data = conn.execute('SELECT name, problem, age, urgency, format FROM anketa_data WHERE user_id = ?', (user_id,)).fetchone()
    
    alias = get_user_alias(user_id)
    report = (f"📋 **НОВАЯ АНКЕТА** ({alias})\n\n"
              f"👤 Имя: {data[0]}\n"
              f"❓ Проблема: {data[1]}\n"
              f"🎂 Возраст: {data[2]}\n"
              f"⚡️ Нужда: {data[3]}\n"
              f"🎧 Формат: {data[4]}")
    
    # Отправка админам и закреп
    sent = bot.send_message(ADMIN_GROUP_ID, report)
    try:
        bot.pin_chat_message(ADMIN_GROUP_ID, sent.message_id)
    except: pass
    
    bot.send_message(user_id, "Спасибо! Теперь расскажи подробнее, что случилось? Я передам всё волонтерам.")

# ОБРАБОТКА ВСЕХ СООБЩЕНИЙ

@bot.message_handler(content_types=['text', 'photo', 'voice', 'document', 'video'])
def main_handler(message):
    user_id = message.chat.id
    state = get_state(user_id)

    # ЛОГИКА ГРУППЫ АДМИНОВ
    if message.chat.id == ADMIN_GROUP_ID:
        if message.reply_to_message:
            u_id = get_user_id_from_link(message.reply_to_message.message_id)
            if u_id:
                try:
                    bot.copy_message(u_id, message.chat.id, message.message_id)
                except:
                    bot.reply_to(message, "❌ Пользователь заблокировал бота.")
        return

    # ЛОГИКА ПОЛЬЗОВАТЕЛЯ (КВИЗ)
    if state == "WAIT_NAME":
        update_anketa(user_id, "name", message.text)
        set_state(user_id, "WAIT_PROBLEM")
        bot.send_message(user_id, "2. Какая основная причина обращения? Напиши кратко или укажи хэштегом (например, #тревога).")
    
    elif state == "WAIT_PROBLEM":
        update_anketa(user_id, "problem", message.text)
        set_state(user_id, "WAIT_AGE")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("10-17", callback_data="quiz_age_1017"),
                   types.InlineKeyboardButton("18-30", callback_data="quiz_age_1830"))
        bot.send_message(user_id, "3. Твой возраст:", reply_markup=markup)

    elif state == "COMPLETED":
        # Пересылка волонтерам (анонимно)
        alias = get_user_alias(user_id)
        bot.send_message(ADMIN_GROUP_ID, f"📩 Сообщение от {alias}:")
        sent = bot.copy_message(ADMIN_GROUP_ID, user_id, message.message_id)
        save_link(sent.message_id, user_id)
    
    else:
        bot.send_message(user_id, "Нажми /start, чтобы начать общение.")

# ЗАПУСК
if __name__ == '__main__':
    init_db()
    bot.remove_webhook()
    print("Бот запущен...")
    bot.infinity_polling()