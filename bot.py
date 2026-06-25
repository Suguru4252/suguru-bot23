import sqlite3
import datetime
import random
import string
import os
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import asyncio

# ==================== КОНФИГ ====================
BOT_TOKEN = "8203822691:AAHCQP2M8imXF0DvqyntA9UdKPE4Y9Fc5eE"
ADMIN_USERNAMES = ["Suguru", "W_u_u_W1", "Dexter"]
ADMIN_PASSWORDS = ["2a3d4g5j", "2a3D4g5J"]
PAYMENT_CARD = "2200153288930010"
PAYMENT_BANK = "Альфа-Банк"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            code TEXT UNIQUE,
            subscription_end TEXT,
            is_admin INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            code TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cur.fetchone()
    conn.close()
    return user

def add_user(user_id, username, first_name):
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    existing = get_user(user_id)
    if not existing:
        code = generate_code()
        cur.execute(
            "INSERT INTO users (user_id, username, first_name, code) VALUES (?, ?, ?, ?)",
            (user_id, username, first_name, code)
        )
        conn.commit()
        conn.close()
        return True, code
    conn.close()
    return False, existing[3]

def generate_code():
    while True:
        code = ''.join(random.choices(string.digits, k=5))
        conn = sqlite3.connect("vpn_bot.db")
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE code = ?", (code,))
        if not cur.fetchone():
            conn.close()
            return code
        conn.close()

def add_payment(user_id, code):
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO payments (user_id, code) VALUES (?, ?)",
        (user_id, code)
    )
    conn.commit()
    conn.close()

def activate_subscription(user_id):
    end_date = (datetime.datetime.now() + datetime.timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET subscription_end = ? WHERE user_id = ?",
        (end_date, user_id)
    )
    cur.execute(
        "UPDATE payments SET status = 'approved' WHERE user_id = ? AND status = 'pending'",
        (user_id,)
    )
    conn.commit()
    conn.close()

def reject_payment_db(user_id):
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    cur.execute(
        "UPDATE payments SET status = 'rejected' WHERE user_id = ? AND status = 'pending'",
        (user_id,)
    )
    conn.commit()
    conn.close()

def get_admins():
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE is_admin = 1")
    admins = [row[0] for row in cur.fetchall()]
    conn.close()
    return admins

def set_admin(user_id):
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_user_by_code(code):
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE code = ?", (code,))
    user = cur.fetchone()
    conn.close()
    return user

# ==================== КЛАВИАТУРЫ ====================
def start_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Оплатить 1₽", callback_data="pay_info")],
        [InlineKeyboardButton(text="🔐 Войти как админ", callback_data="admin_login")]
    ])

def admin_decision_keyboard(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Выдать ссылку", callback_data=f"approve_{user_id}"),
            InlineKeyboardButton(text="❌ Не выдавать", callback_data=f"reject_{user_id}")
        ]
    ])

# ==================== СОСТОЯНИЯ FSM ====================
class AdminAuth(StatesGroup):
    waiting_for_username = State()
    waiting_for_password = State()

class AdminSendLink(StatesGroup):
    waiting_for_link = State()

class AdminRejectReason(StatesGroup):
    waiting_for_reason = State()

# Временное хранилище для user_id в FSM
admin_temp_data = {}

# ==================== ХЕНДЛЕРЫ ПОЛЬЗОВАТЕЛЯ ====================
@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "unknown"
    first_name = message.from_user.first_name or "unknown"
    
    is_new, code = add_user(user_id, username, first_name)
    
    if is_new:
        # Уведомляем админов о новом пользователе
        admins = get_admins()
        for admin_id in admins:
            try:
                await bot.send_message(
                    admin_id,
                    f"🆕 Новый пользователь!\n"
                    f"Username: @{username}\n"
                    f"Имя: {first_name}\n"
                    f"Код: {code}"
                )
            except:
                pass
    
    await message.answer(
        f"👋 Добро пожаловать в <b>ChugurVPN</b>!\n\n"
        f"🎁 Чтобы получить <b>3 дня бесплатно</b>, нужно подтвердить, "
        f"что вы готовы сотрудничать и доверять нам.\n\n"
        f"🔑 Ваш персональный код: <b><code>{code}</code></b>\n\n"
        f"⚠️ <b>ГЛАВНОЕ ЗАПОМНИТЕ ЭТОТ КОД!</b> "
        f"Он понадобится для активации VPN.\n\n"
        f"💳 Чтобы начать пробный период, нужно сделать вклад "
        f"в размере <b>1₽</b> для подтверждения аккаунта.\n\n"
        f"🏦 <b>{PAYMENT_BANK}</b>: <code>{PAYMENT_CARD}</code>\n\n"
        f"📝 <b>Главное!</b> Напишите в сообщении перевода свои "
        f"<b>5 эксклюзивных цифр</b>, чтобы мы могли понять, "
        f"от кого был сделан перевод.\n\n"
        f"⏳ После оплаты вы встаёте на модерацию. "
        f"Через 5-10 минут бот пришлёт вам ссылку на VPN.\n"
        f"🔄 Через 3 дня доступ исчезнет, и нужно будет продлевать.",
        reply_markup=start_keyboard()
    )

@router.callback_query(F.data == "pay_info")
async def pay_info(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = get_user(user_id)
    code = user[3]
    
    add_payment(user_id, code)
    
    # Уведомляем админов
    admins = get_admins()
    for admin_id in admins:
        try:
            await bot.send_message(
                admin_id,
                f"💳 Пользователь хочет оплатить!\n"
                f"Username: @{callback.from_user.username}\n"
                f"Код: <b>{code}</b>",
                reply_markup=admin_decision_keyboard(user_id)
            )
        except:
            pass
    
    await callback.message.answer(
        f"✅ Отлично! Ваш код для оплаты: <b>{code}</b>\n\n"
        f"💳 Переведите <b>1₽</b> на карту:\n"
        f"<code>{PAYMENT_CARD}</code> ({PAYMENT_BANK})\n\n"
        f"📝 В сообщении перевода укажите код: <b>{code}</b>\n\n"
        f"⏳ После проверки вам придёт ссылка на VPN."
    )
    await callback.answer()

# ==================== ХЕНДЛЕРЫ АДМИНА ====================
@router.callback_query(F.data == "admin_login")
async def admin_login_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("👤 Введите секретный никнейм админа:")
    await state.set_state(AdminAuth.waiting_for_username)
    await callback.answer()

@router.message(AdminAuth.waiting_for_username)
async def admin_username(message: Message, state: FSMContext):
    if message.text in ADMIN_USERNAMES:
        await state.update_data(username=message.text)
        await message.answer("🔑 Теперь введите пароль:")
        await state.set_state(AdminAuth.waiting_for_password)
    else:
        await message.answer("❌ Неверный никнейм. Попробуйте ещё раз.")
        await state.set_state(AdminAuth.waiting_for_username)

@router.message(AdminAuth.waiting_for_password)
async def admin_password(message: Message, state: FSMContext):
    if message.text in ADMIN_PASSWORDS:
        user_id = message.from_user.id
        set_admin(user_id)
        await message.answer("✅ Вы успешно вошли как администратор!")
        
        # Отправляем приветствие админу
        await message.answer(
            "📋 <b>Админ-панель</b>\n\n"
            "Вы будете получать уведомления:\n"
            "1️⃣ Когда новый пользователь заходит в бота\n"
            "2️⃣ Когда пользователь нажимает «Оплатить»\n"
            "3️⃣ Когда заканчивается подписка\n\n"
            "Команды:\n"
            "/check_expired - проверить истекшие подписки"
        )
    else:
        await message.answer("❌ Неверный пароль. Попробуйте ещё раз.")
        await state.set_state(AdminAuth.waiting_for_password)
    
    await state.clear()

@router.callback_query(F.data.startswith("approve_"))
async def approve_payment(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[1])
    admin_temp_data[callback.from_user.id] = user_id
    
    await callback.message.answer(
        f"🔗 Введите ссылку, которую хотите отправить пользователю:"
    )
    await state.set_state(AdminSendLink.waiting_for_link)
    await callback.answer()

@router.message(AdminSendLink.waiting_for_link)
async def send_link_to_user(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    user_id = admin_temp_data.get(admin_id)
    
    if user_id:
        activate_subscription(user_id)
        
        try:
            await bot.send_message(
                user_id,
                f"✅ Ваш платёж подтверждён!\n"
                f"🔗 Ссылка на VPN: {message.text}\n\n"
                f"⏰ Доступ активен на 3 дня."
            )
            await message.answer("✅ Ссылка отправлена пользователю!")
        except:
            await message.answer("❌ Не удалось отправить сообщение пользователю.")
    else:
        await message.answer("❌ Ошибка: пользователь не найден.")
    
    await state.clear()

@router.callback_query(F.data.startswith("reject_"))
async def reject_payment(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[1])
    admin_temp_data[callback.from_user.id] = user_id
    
    await callback.message.answer(
        "📝 Напишите причину отказа:"
    )
    await state.set_state(AdminRejectReason.waiting_for_reason)
    await callback.answer()

@router.message(AdminRejectReason.waiting_for_reason)
async def send_reject_reason(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    user_id = admin_temp_data.get(admin_id)
    
    if user_id:
        reject_payment_db(user_id)
        
        try:
            await bot.send_message(
                user_id,
                f"❌ Ваш запрос отклонён модератором.\n"
                f"📝 Причина: {message.text}"
            )
            await message.answer("✅ Уведомление об отказе отправлено!")
        except:
            await message.answer("❌ Не удалось отправить сообщение пользователю.")
    else:
        await message.answer("❌ Ошибка: пользователь не найден.")
    
    await state.clear()

@router.message(Command("check_expired"))
async def check_expired(message: Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if user and user[5] == 1:  # is_admin = 1
        conn = sqlite3.connect("vpn_bot.db")
        cur = conn.cursor()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "SELECT user_id, code, subscription_end FROM users WHERE subscription_end IS NOT NULL AND subscription_end <= ?",
            (now,)
        )
        expired = cur.fetchall()
        conn.close()
        
        if expired:
            await message.answer(f"⚠️ Истекшие подписки: {len(expired)}")
            for u in expired:
                await message.answer(
                    f"👤 ID: {u[0]}\n"
                    f"🔑 Код: {u[1]}\n"
                    f"📅 Истекла: {u[2]}"
                )
        else:
            await message.answer("✅ Нет истекших подписок.")
    else:
        await message.answer("❌ У вас нет прав администратора.")

# ==================== ПРОВЕРКА ПОДПИСОК ====================
async def check_subscriptions():
    while True:
        admins = get_admins()
        conn = sqlite3.connect("vpn_bot.db")
        cur = conn.cursor()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "SELECT user_id, code FROM users WHERE subscription_end IS NOT NULL AND subscription_end <= ?",
            (now,)
        )
        expired = cur.fetchall()
        conn.close()
        
        for user_id, code in expired:
            for admin_id in admins:
                try:
                    await bot.send_message(
                        admin_id,
                        f"⏰ <b>Подписка истекла!</b>\n"
                        f"👤 Пользователь: {user_id}\n"
                        f"🔑 Код: {code}"
                    )
                except:
                    pass
            
            # Уведомляем пользователя
            try:
                await bot.send_message(
                    user_id,
                    "⏰ Ваша подписка на VPN истекла.\n"
                    "Для продления обратитесь к администратору."
                )
            except:
                pass
        
        await asyncio.sleep(300)  # Проверка каждые 5 минут

# ==================== ЗАПУСК ====================
async def main():
    init_db()
    dp.include_router(router)
    
    # Запускаем фоновую проверку подписок
    asyncio.create_task(check_subscriptions())
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
