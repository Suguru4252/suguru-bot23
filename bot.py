import sqlite3
import datetime
import random
import string
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import asyncio
import re

# ==================== КОНФИГ ====================
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "8203822691:AAHCQP2M8imXF0DvqyntA9UdKPE4Y9Fc5eE")

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
            personal_code TEXT UNIQUE,
            subscription_end TEXT,
            is_admin INTEGER DEFAULT 0,
            has_active_sub INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            personal_code TEXT,
            status TEXT DEFAULT 'pending',
            subscription_days INTEGER DEFAULT 3,
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
        code = generate_unique_code()
        cur.execute(
            "INSERT INTO users (user_id, username, first_name, personal_code) VALUES (?, ?, ?, ?)",
            (user_id, username, first_name, code)
        )
        conn.commit()
        conn.close()
        return True, code
    conn.close()
    return False, existing[3]

def generate_unique_code():
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    cur.execute("SELECT personal_code FROM users")
    existing_codes = {row[0] for row in cur.fetchall()}
    conn.close()

    while True:
        code = ''.join(random.choices(string.digits, k=5))
        if code not in existing_codes:
            return code

def add_payment(user_id, code, days=3):
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO payments (user_id, personal_code, subscription_days) VALUES (?, ?, ?)",
        (user_id, code, days)
    )
    conn.commit()
    conn.close()

def activate_subscription(user_id, end_date_str):
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET subscription_end = ?, has_active_sub = 1 WHERE user_id = ?",
        (end_date_str, user_id)
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

def extend_subscription(user_id, days):
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    user = get_user(user_id)
    if user and user[4]:
        current_end = datetime.datetime.strptime(user[4], "%Y-%m-%d %H:%M")
        new_end = current_end + datetime.timedelta(days=days)
        new_end_str = new_end.strftime("%Y-%m-%d %H:%M")
        cur.execute("UPDATE users SET subscription_end = ? WHERE user_id = ?", (new_end_str, user_id))
    else:
        new_end = datetime.datetime.now() + datetime.timedelta(days=days)
        new_end_str = new_end.strftime("%Y-%m-%d %H:%M")
        cur.execute("UPDATE users SET subscription_end = ?, has_active_sub = 1 WHERE user_id = ?", (new_end_str, user_id))
    conn.commit()
    conn.close()

def cancel_subscription(user_id):
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    cur.execute("UPDATE users SET subscription_end = NULL, has_active_sub = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_user_by_code(code):
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE personal_code = ?", (code,))
    user = cur.fetchone()
    conn.close()
    return user

# ==================== КЛАВИАТУРЫ ====================
def main_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Я оплатил", callback_data="pay_confirm")],
        [InlineKeyboardButton(text="❌ Я отказываюсь", callback_data="pay_reject")],
        [InlineKeyboardButton(text="🔐 Админ панель", callback_data="admin_login")]
    ])

def admin_decision_keyboard(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Выдать ссылку", callback_data=f"approve_{user_id}"),
            InlineKeyboardButton(text="❌ Отказ", callback_data=f"reject_{user_id}")
        ]
    ])

def subscription_expired_keyboard(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔒 Забрать подписку", callback_data=f"take_{user_id}"),
            InlineKeyboardButton(text="🔄 Оставить (+1 день)", callback_data=f"keep_{user_id}")
        ]
    ])

def renew_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Я оплатил 50₽", callback_data="renew_paid")],
        [InlineKeyboardButton(text="❌ Отказаться", callback_data="renew_reject")]
    ])

# ==================== FSM ====================
class AdminAuth(StatesGroup):
    waiting_for_username = State()
    waiting_for_password = State()

class AdminSendLink(StatesGroup):
    waiting_for_link = State()
    waiting_for_date = State()

class AdminRejectReason(StatesGroup):
    waiting_for_reason = State()

admin_temp_data = {}

# ==================== ХЕНДЛЕРЫ ====================

@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "unknown"
    first_name = message.from_user.first_name or "unknown"

    is_new, code = add_user(user_id, username, first_name)

    if is_new:
        admins = get_admins()
        for admin_id in admins:
            try:
                await bot.send_message(
                    admin_id,
                    f"🆕 Новый пользователь!\n"
                    f"👤 @{username}\n"
                    f"📛 {first_name}\n"
                    f"🔑 Код: <b>{code}</b>"
                )
            except:
                pass

    await message.answer(
        f"👋 Добро пожаловать в <b>ChugurVPN</b>!\n\n"
        f"⚠️ <b>ВНИМАНИЕ!</b> Ваш персональный номер:\n"
        f"🔑 <b><code>{code}</code></b>\n\n"
        f"📌 <b>ЗАПОМНИТЕ ЕГО!</b> Он нужен для подтверждения оплаты.\n\n"
        f"🎁 За первое посещение мы дарим вам <b>3 дня пробной подписки!</b>\n\n"
        f"💳 Для активации оплатите <b>1₽</b> на реквизиты:\n"
        f"🏦 <b>{PAYMENT_BANK}</b>\n"
        f"💳 <code>{PAYMENT_CARD}</code>\n\n"
        f"📝 <b>В сообщении перевода укажите ваш персональный номер: <code>{code}</code></b>",
        reply_markup=main_menu_keyboard()
    )

# ==================== ОПЛАТА ====================
@router.callback_query(F.data == "pay_confirm")
async def pay_confirm(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = get_user(user_id)
    code = user[3]

    add_payment(user_id, code, days=3)

    admins = get_admins()
    for admin_id in admins:
        try:
            await bot.send_message(
                admin_id,
                f"💳 <b>Новая оплата!</b>\n"
                f"🔑 Персональный номер: <b>{code}</b>\n"
                f"👤 @{callback.from_user.username}",
                reply_markup=admin_decision_keyboard(user_id)
            )
        except:
            pass

    await callback.message.answer("✅ Ваш платёж отправлен на модерацию. Ожидайте.")
    await callback.answer()

@router.callback_query(F.data == "pay_reject")
async def pay_reject(callback: CallbackQuery):
    await callback.message.answer("👋 Когда созреете — приходите ещё, мы всегда рады!")
    await callback.answer()

# ==================== ПРОДЛЕНИЕ ====================
@router.callback_query(F.data == "renew_paid")
async def renew_paid(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = get_user(user_id)
    code = user[3]

    add_payment(user_id, code, days=30)

    admins = get_admins()
    for admin_id in admins:
        try:
            await bot.send_message(
                admin_id,
                f"💳 <b>Продление подписки!</b>\n"
                f"🔑 Персональный номер: <b>{code}</b>\n"
                f"👤 @{callback.from_user.username}\n"
                f"💰 Сумма: 50₽",
                reply_markup=admin_decision_keyboard(user_id)
            )
        except:
            pass

    await callback.message.answer("✅ Ваш платёж на продление отправлен на модерацию.")
    await callback.answer()

@router.callback_query(F.data == "renew_reject")
async def renew_reject(callback: CallbackQuery):
    await callback.message.answer("👋 Будем ждать вас снова!")
    await callback.answer()

# ==================== АДМИН ЛОГИН ====================
@router.callback_query(F.data == "admin_login")
async def admin_login(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("👤 Введите секретный никнейм:")
    await state.set_state(AdminAuth.waiting_for_username)
    await callback.answer()

@router.message(AdminAuth.waiting_for_username)
async def check_username(message: Message, state: FSMContext):
    if message.text in ADMIN_USERNAMES:
        await state.update_data(username=message.text)
        await message.answer("🔑 Введите пароль:")
        await state.set_state(AdminAuth.waiting_for_password)
    else:
        await message.answer("❌ Неверный никнейм!")

@router.message(AdminAuth.waiting_for_password)
async def check_password(message: Message, state: FSMContext):
    if message.text in ADMIN_PASSWORDS:
        user_id = message.from_user.id
        set_admin(user_id)
        await message.answer(
            "✅ <b>Добро пожаловать в админ-панель!</b>\n\n"
            "📋 Вы будете получать уведомления об оплатах и истечении подписок."
        )
    else:
        await message.answer("❌ Неверный пароль!")
    await state.clear()

# ==================== АДМИН: ВЫДАТЬ ССЫЛКУ ====================
@router.callback_query(F.data.startswith("approve_"))
async def approve_payment(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[1])
    admin_temp_data[callback.from_user.id] = {"user_id": user_id}
    await callback.message.answer("🔗 Отправьте ссылку (или любое сообщение) для пользователя:")
    await state.set_state(AdminSendLink.waiting_for_link)
    await callback.answer()

@router.message(AdminSendLink.waiting_for_link)
async def get_link(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    data = admin_temp_data.get(admin_id, {})
    data["link"] = message.text
    admin_temp_data[admin_id] = data

    await message.answer(
        "📅 Укажите дату истечения подписки в формате:\n"
        "<code>ДД:ММ:ГГГГ ЧЧ:ММ</code>\n\n"
        "Например: <code>15:12:2026 14:30</code>"
    )
    await state.set_state(AdminSendLink.waiting_for_date)

@router.message(AdminSendLink.waiting_for_date)
async def get_date_and_send(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    data = admin_temp_data.get(admin_id, {})
    user_id = data.get("user_id")
    link = data.get("link")

    date_pattern = r"^\d{2}:\d{2}:\d{4} \d{2}:\d{2}$"
    if not re.match(date_pattern, message.text):
        await message.answer("❌ Неверный формат! Используйте: ДД:ММ:ГГГГ ЧЧ:ММ")
        return

    try:
        end_date = datetime.datetime.strptime(message.text, "%d:%m:%Y %H:%M")
        end_date_str = end_date.strftime("%Y-%m-%d %H:%M")
    except:
        await message.answer("❌ Некорректная дата!")
        return

    if user_id:
        activate_subscription(user_id, end_date_str)

        try:
            await bot.send_message(
                user_id,
                f"✅ <b>Подписка активирована!</b>\n\n"
                f"{link}\n\n"
                f"⏰ Действует до: <b>{end_date.strftime('%d.%m.%Y %H:%M')}</b>"
            )
            await message.answer("✅ Сообщение отправлено пользователю!")
        except:
            await message.answer("❌ Не удалось отправить сообщение.")

    await state.clear()

# ==================== АДМИН: ОТКАЗ ====================
@router.callback_query(F.data.startswith("reject_"))
async def reject_payment(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[1])
    admin_temp_data[callback.from_user.id] = {"user_id": user_id}
    await callback.message.answer("📝 Напишите причину отказа:")
    await state.set_state(AdminRejectReason.waiting_for_reason)
    await callback.answer()

@router.message(AdminRejectReason.waiting_for_reason)
async def send_reject(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    user_id = admin_temp_data.get(admin_id, {}).get("user_id")

    if user_id:
        reject_payment_db(user_id)
        try:
            await bot.send_message(
                user_id,
                f"❌ <b>Запрос отклонён.</b>\n\n📝 Причина: {message.text}"
            )
            await message.answer("✅ Уведомление отправлено!")
        except:
            await message.answer("❌ Ошибка отправки.")

    await state.clear()

# ==================== АДМИН: ИСТЕЧЕНИЕ ПОДПИСКИ ====================
@router.callback_query(F.data.startswith("take_"))
async def take_subscription(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    cancel_subscription(user_id)

    try:
        await bot.send_message(
            user_id,
            f"⏰ <b>Подписка закончилась!</b>\n\n"
            f"💳 Чтобы продлить — оплатите <b>50₽</b>:\n"
            f"🏦 {PAYMENT_BANK}\n"
            f"💳 <code>{PAYMENT_CARD}</code>\n\n"
            f"📝 В сообщении укажите ваш код: <b>{get_user(user_id)[3]}</b>",
            reply_markup=renew_menu_keyboard()
        )
        await callback.message.answer("✅ Подписка забрана. Пользователю отправлено уведомление.")
    except:
        await callback.message.answer("❌ Ошибка отправки пользователю.")

    await callback.answer()

@router.callback_query(F.data.startswith("keep_"))
async def keep_subscription(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    extend_subscription(user_id, 1)

    try:
        await bot.send_message(
            user_id,
            "🎁 <b>Подписка продлена на 1 день!</b>\nСпасибо что вы с нами!"
        )
        await callback.message.answer("✅ Подписка продлена на 1 день.")
    except:
        await callback.message.answer("❌ Ошибка отправки.")

    await callback.answer()

# ==================== ФОНОВАЯ ПРОВЕРКА ====================
async def check_subscriptions():
    while True:
        admins = get_admins()
        conn = sqlite3.connect("vpn_bot.db")
        cur = conn.cursor()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        cur.execute(
            "SELECT user_id, personal_code FROM users WHERE subscription_end IS NOT NULL AND subscription_end <= ?",
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
                        f"🔑 Код: <b>{code}</b>\n"
                        f"👤 ID: {user_id}",
                        reply_markup=subscription_expired_keyboard(user_id)
                    )
                except:
                    pass

        await asyncio.sleep(60)  # Проверка каждую минуту

# ==================== ЗАПУСК ====================
async def main():
    init_db()
    dp.include_router(router)
    asyncio.create_task(check_subscriptions())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
