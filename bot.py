import sqlite3
import datetime
import random
import string
import asyncio
import re
import uuid
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ==================== КОНФИГ ====================
BOT_TOKEN = "8203822691:AAHriNfGaWY2ppCZ6bkEM5LpM_pprFyW8OM"
BOT_USERNAME = "ChugurVPNBot"  # Замени на юзернейм своего бота без @

ADMIN_USERNAMES = ["Suguru", "W_u_u_W1", "Dexter"]
ADMIN_PASSWORDS = ["2a3d4g5j", "2a3D4g5J"]
PAYMENT_CARD = "2200153288930010"
PAYMENT_BANK = "Альфа-Банк"

# Тарифы
TARIFFS = {
    "14_days": {"name": "14 дней", "price": 50, "days": 14},
    "1_month": {"name": "1 месяц", "price": 90, "days": 30},
    "2_months": {"name": "2 месяца", "price": 180, "days": 60},
    "6_months": {"name": "6 месяцев", "price": 800, "days": 180},
    "1_year": {"name": "1 год", "price": 1200, "days": 365},
}

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
            subscription_link TEXT,
            is_admin INTEGER DEFAULT 0,
            has_active_sub INTEGER DEFAULT 0,
            ref_code TEXT UNIQUE,
            ref_by INTEGER,
            ref_bonus_given INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            personal_code TEXT,
            tariff TEXT,
            price INTEGER,
            days INTEGER,
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

def add_user(user_id, username, first_name, ref_code=None):
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    existing = get_user(user_id)
    if not existing:
        code = generate_unique_code()
        ref = str(uuid.uuid4())[:8]
        ref_by = None
        
        # Если пришёл по реферальной ссылке
        if ref_code:
            cur.execute("SELECT user_id FROM users WHERE ref_code = ?", (ref_code,))
            referrer = cur.fetchone()
            if referrer:
                ref_by = referrer[0]
        
        cur.execute(
            "INSERT INTO users (user_id, username, first_name, personal_code, ref_code, ref_by) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, first_name, code, ref, ref_by)
        )
        conn.commit()
        conn.close()
        return True, code, ref, ref_by
    conn.close()
    return False, existing[3], existing[6], existing[7]

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

def add_payment(user_id, code, tariff, price, days):
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO payments (user_id, personal_code, tariff, price, days) VALUES (?, ?, ?, ?, ?)",
        (user_id, code, tariff, price, days)
    )
    conn.commit()
    conn.close()

def activate_subscription(user_id, link, end_date_str, days):
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    
    user = get_user(user_id)
    if user and user[4]:
        # Продление существующей подписки
        current_end = datetime.datetime.strptime(user[4], "%d:%m:%Y %H:%M")
        new_end = current_end + datetime.timedelta(days=days)
        new_end_str = new_end.strftime("%d:%m:%Y %H:%M")
    else:
        new_end = datetime.datetime.now() + datetime.timedelta(days=days)
        new_end_str = new_end.strftime("%d:%m:%Y %H:%M")
    
    cur.execute(
        "UPDATE users SET subscription_end = ?, subscription_link = ?, has_active_sub = 1 WHERE user_id = ?",
        (new_end_str, link, user_id)
    )
    cur.execute(
        "UPDATE payments SET status = 'approved' WHERE user_id = ? AND status = 'pending'",
        (user_id,)
    )
    conn.commit()
    conn.close()
    return new_end_str

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

def cancel_subscription(user_id):
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    cur.execute("UPDATE users SET subscription_end = NULL, subscription_link = NULL, has_active_sub = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def extend_subscription(user_id, days):
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    user = get_user(user_id)
    if user and user[4]:
        current_end = datetime.datetime.strptime(user[4], "%d:%m:%Y %H:%M")
        new_end = current_end + datetime.timedelta(days=days)
        new_end_str = new_end.strftime("%d:%m:%Y %H:%M")
        cur.execute("UPDATE users SET subscription_end = ? WHERE user_id = ?", (new_end_str, user_id))
    else:
        new_end = datetime.datetime.now() + datetime.timedelta(days=days)
        new_end_str = new_end.strftime("%d:%m:%Y %H:%M")
        cur.execute("UPDATE users SET subscription_end = ?, has_active_sub = 1 WHERE user_id = ?", (new_end_str, user_id))
    conn.commit()
    conn.close()

def give_ref_bonus(user_id):
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    cur.execute("UPDATE users SET ref_bonus_given = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_all_active_subscriptions():
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id, personal_code, username, subscription_end, subscription_link FROM users WHERE has_active_sub = 1")
    subs = cur.fetchall()
    conn.close()
    return subs

def get_pending_payments():
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    cur.execute("SELECT p.user_id, p.personal_code, u.username, p.tariff, p.price FROM payments p JOIN users u ON p.user_id = u.user_id WHERE p.status = 'pending'")
    pending = cur.fetchall()
    conn.close()
    return pending

# ==================== КЛАВИАТУРЫ ====================
def main_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Выбрать тариф", callback_data="select_tariff")],
        [InlineKeyboardButton(text="👥 Реферальная ссылка", callback_data="ref_info")],
        [InlineKeyboardButton(text="🔐 Админ панель", callback_data="admin_login")]
    ])

def tariff_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 14 дней - 50₽", callback_data="tariff_14_days")],
        [InlineKeyboardButton(text="📅 1 месяц - 90₽", callback_data="tariff_1_month")],
        [InlineKeyboardButton(text="📅 2 месяца - 180₽", callback_data="tariff_2_months")],
        [InlineKeyboardButton(text="📅 6 месяцев - 800₽", callback_data="tariff_6_months")],
        [InlineKeyboardButton(text="📅 1 год - 1200₽", callback_data="tariff_1_year")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

def admin_decision_keyboard(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Выдать ссылку", callback_data=f"approve_{user_id}"),
            InlineKeyboardButton(text="❌ Отказ", callback_data=f"reject_{user_id}")
        ]
    ])

def admin_panel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Все активные подписки", callback_data="admin_list_subs")],
        [InlineKeyboardButton(text="📝 Ожидают модерации", callback_data="admin_list_pending")]
    ])

def subscription_action_keyboard(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔒 Забрать подписку", callback_data=f"take_{user_id}"),
            InlineKeyboardButton(text="🔄 Продлить на 1 день", callback_data=f"keep_{user_id}")
        ]
    ])

def ref_bonus_keyboard(ref_by, new_user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Выдать +1 день", callback_data=f"refbonus_{ref_by}_{new_user_id}")]
    ])

def back_to_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")]
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

class AdminTakeReason(StatesGroup):
    waiting_for_reason = State()

admin_temp_data = {}

# ==================== ХЕНДЛЕРЫ ====================

@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "unknown"
    first_name = message.from_user.first_name or "unknown"

    # Проверяем реферальный код
    ref_code = None
    args = message.text.split()
    if len(args) > 1:
        ref_code = args[1]

    is_new, code, ref, ref_by = add_user(user_id, username, first_name, ref_code)

    if is_new:
        # Уведомляем админов
        admins = get_admins()
        for admin_id in admins:
            try:
                await bot.send_message(
                    admin_id,
                    f"Новый пользователь!\n"
                    f"Ник: @{username}\n"
                    f"Имя: {first_name}\n"
                    f"Код: {code}"
                )
            except:
                pass

        # Если пришёл по рефералке - уведомляем админов
        if ref_by and ref_by != user_id:
            ref_user = get_user(ref_by)
            if ref_user:
                for admin_id in admins:
                    try:
                        await bot.send_message(
                            admin_id,
                            f"Реферал!\n"
                            f"Пользователь @{ref_user[1]} (код: {ref_user[3]}) пригласил @{username}\n"
                            f"Начислить +1 день?",
                            reply_markup=ref_bonus_keyboard(ref_by, user_id)
                        )
                    except:
                        pass

    await message.answer(
        f"Добро пожаловать в ChugurVPN!\n\n"
        f"ВНИМАНИЕ! Ваш персональный номер:\n"
        f"{code}\n\n"
        f"ЗАПОМНИТЕ ЕГО! Он нужен для подтверждения оплаты.\n\n"
        f"Выберите действие:",
        reply_markup=main_menu_keyboard()
    )

# ==================== ВЫБОР ТАРИФА ====================
@router.callback_query(F.data == "select_tariff")
async def select_tariff(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("Выберите тариф:", reply_markup=tariff_keyboard())

@router.callback_query(F.data.startswith("tariff_"))
async def tariff_selected(callback: CallbackQuery):
    tariff_key = callback.data.replace("tariff_", "")
    tariff = TARIFFS.get(tariff_key)

    if not tariff:
        await callback.answer("Тариф не найден!", show_alert=True)
        return

    user_id = callback.from_user.id
    user = get_user(user_id)
    code = user[3]

    add_payment(user_id, code, tariff["name"], tariff["price"], tariff["days"])

    admins = get_admins()
    for admin_id in admins:
        try:
            await bot.send_message(
                admin_id,
                f"Новая оплата!\n"
                f"Тариф: {tariff['name']}\n"
                f"Сумма: {tariff['price']}₽\n"
                f"Персональный номер: {code}\n"
                f"Ник: @{callback.from_user.username}",
                reply_markup=admin_decision_keyboard(user_id)
            )
        except:
            pass

    await callback.answer()
    await callback.message.answer(
        f"Вы выбрали тариф: {tariff['name']}\n"
        f"Сумма к оплате: {tariff['price']}₽\n\n"
        f"Оплатите на реквизиты:\n"
        f"Банк: {PAYMENT_BANK}\n"
        f"Карта: {PAYMENT_CARD}\n\n"
        f"В сообщении перевода укажите ваш код: {code}\n\n"
        f"Ожидайте подтверждения от модератора.",
        reply_markup=back_to_main_keyboard()
    )

# ==================== РЕФЕРАЛЬНАЯ ССЫЛКА ====================
@router.callback_query(F.data == "ref_info")
async def ref_info(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = get_user(user_id)
    ref_code = user[6]
    
    ref_link = f"https://t.me/{BOT_USERNAME}?start={ref_code}"
    
    await callback.answer()
    await callback.message.answer(
        f"Ваша реферальная ссылка:\n"
        f"{ref_link}\n\n"
        f"За каждого приглашённого пользователя вы получаете +1 день к подписке!\n\n"
        f"Отправьте эту ссылку друзьям и получайте бонусы.",
        reply_markup=back_to_main_keyboard()
    )

# ==================== НАЗАД В МЕНЮ ====================
@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("Главное меню:", reply_markup=main_menu_keyboard())

# ==================== АДМИН ЛОГИН ====================
@router.callback_query(F.data == "admin_login")
async def admin_login(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("Введите секретный никнейм:")
    await state.set_state(AdminAuth.waiting_for_username)

@router.message(AdminAuth.waiting_for_username)
async def check_username(message: Message, state: FSMContext):
    if message.text in ADMIN_USERNAMES:
        await state.update_data(username=message.text)
        await message.answer("Введите пароль:")
        await state.set_state(AdminAuth.waiting_for_password)
    else:
        await message.answer("Неверный никнейм! Попробуйте ещё раз или нажмите /start для выхода.")

@router.message(AdminAuth.waiting_for_password)
async def check_password(message: Message, state: FSMContext):
    if message.text in ADMIN_PASSWORDS:
        user_id = message.from_user.id
        set_admin(user_id)
        await message.answer(
            "Добро пожаловать в админ-панель!\n\nВыберите действие:",
            reply_markup=admin_panel_keyboard()
        )
        await state.clear()
    else:
        await message.answer("Неверный пароль! Попробуйте ещё раз или нажмите /start для выхода.")

# ==================== АДМИН: МЕНЮ ====================
@router.callback_query(F.data == "admin_list_subs")
async def admin_list_subs(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user or user[5] != 1:
        await callback.answer("Нет доступа!", show_alert=True)
        return

    await callback.answer()
    subs = get_all_active_subscriptions()

    if not subs:
        await callback.message.answer("Нет активных подписок.")
        return

    for sub in subs:
        user_id, code, username, end_date, link = sub
        await callback.message.answer(
            f"Активная подписка:\n"
            f"Код: {code}\n"
            f"Ник: @{username}\n"
            f"Ссылка: {link}\n"
            f"Истекает: {end_date}",
            reply_markup=subscription_action_keyboard(user_id)
        )

@router.callback_query(F.data == "admin_list_pending")
async def admin_list_pending(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user or user[5] != 1:
        await callback.answer("Нет доступа!", show_alert=True)
        return

    await callback.answer()
    pending = get_pending_payments()

    if not pending:
        await callback.message.answer("Нет ожидающих модерации.")
        return

    for user_id, code, username, tariff, price in pending:
        await callback.message.answer(
            f"Ожидает модерации:\n"
            f"Код: {code}\n"
            f"Ник: @{username}\n"
            f"Тариф: {tariff}\n"
            f"Сумма: {price}₽",
            reply_markup=admin_decision_keyboard(user_id)
        )

# ==================== АДМИН: ВЫДАТЬ ССЫЛКУ ====================
@router.callback_query(F.data.startswith("approve_"))
async def approve_payment(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[1])
    admin_temp_data[callback.from_user.id] = {"user_id": user_id}
    await callback.answer()
    await callback.message.answer("Отправьте ссылку (или любое сообщение) для пользователя:")
    await state.set_state(AdminSendLink.waiting_for_link)

@router.message(AdminSendLink.waiting_for_link)
async def get_link(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    data = admin_temp_data.get(admin_id, {})
    data["link"] = message.text
    admin_temp_data[admin_id] = data

    now = datetime.datetime.now()
    await message.answer(
        f"Укажите дату истечения подписки в формате:\n"
        f"ДД:ММ:ГГГГ ЧЧ:ММ\n\n"
        f"Например: {now.strftime('%d:%m:%Y %H:%M')}"
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
        await message.answer("Неверный формат! Используйте: ДД:ММ:ГГГГ ЧЧ:ММ")
        return

    try:
        end_date = datetime.datetime.strptime(message.text, "%d:%m:%Y %H:%M")
        end_date_str = end_date.strftime("%d:%m:%Y %H:%M")
    except:
        await message.answer("Некорректная дата!")
        return

    if user_id:
        # Получаем дни из последнего платежа
        conn = sqlite3.connect("vpn_bot.db")
        cur = conn.cursor()
        cur.execute("SELECT days FROM payments WHERE user_id = ? AND status = 'pending' ORDER BY created_at DESC LIMIT 1", (user_id,))
        payment = cur.fetchone()
        conn.close()
        
        days = payment[0] if payment else 3
        activate_subscription(user_id, link, end_date_str, days)

        try:
            await bot.send_message(
                user_id,
                f"Подписка активирована!\n\n"
                f"{link}\n\n"
                f"Действует до: {end_date_str}"
            )
            await message.answer(f"Готово! Подписка активна до {end_date_str}")
        except:
            await message.answer("Не удалось отправить сообщение пользователю.")

    await state.clear()

# ==================== АДМИН: ОТКАЗ ====================
@router.callback_query(F.data.startswith("reject_"))
async def reject_payment(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[1])
    await state.update_data(user_id=user_id)
    await callback.answer()
    await callback.message.answer("Напишите причину отказа:")
    await state.set_state(AdminRejectReason.waiting_for_reason)

@router.message(AdminRejectReason.waiting_for_reason)
async def send_reject(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")

    if user_id:
        reject_payment_db(user_id)
        try:
            await bot.send_message(
                user_id,
                f"Запрос отклонён.\n\nПричина: {message.text}"
            )
            await message.answer("Уведомление отправлено!")
        except:
            await message.answer("Ошибка отправки.")

    await state.clear()

# ==================== АДМИН: ЗАБРАТЬ ПОДПИСКУ ====================
@router.callback_query(F.data.startswith("take_"))
async def take_subscription_start(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[1])
    await state.update_data(user_id=user_id)
    await callback.answer()
    await callback.message.answer("Напишите причину почему забираете подписку:")
    await state.set_state(AdminTakeReason.waiting_for_reason)

@router.message(AdminTakeReason.waiting_for_reason)
async def take_subscription_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")

    if user_id:
        user = get_user(user_id)
        code = user[3]
        cancel_subscription(user_id)

        try:
            await bot.send_message(
                user_id,
                f"Подписка закончилась!\n"
                f"Причина: {message.text}\n\n"
                f"Чтобы продлить - выберите тариф в главном меню.",
                reply_markup=back_to_main_keyboard()
            )
            await message.answer("Подписка забрана. Пользователь уведомлён.")
        except:
            await message.answer("Ошибка отправки пользователю.")

    await state.clear()

# ==================== АДМИН: ПРОДЛИТЬ ====================
@router.callback_query(F.data.startswith("keep_"))
async def keep_subscription(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    extend_subscription(user_id, 1)

    try:
        await bot.send_message(
            user_id,
            "Подписка продлена на 1 день! Спасибо что вы с нами!"
        )
        await callback.answer("Подписка продлена на 1 день.", show_alert=True)
    except:
        await callback.answer("Ошибка отправки.", show_alert=True)

# ==================== АДМИН: РЕФЕРАЛЬНЫЙ БОНУС ====================
@router.callback_query(F.data.startswith("refbonus_"))
async def ref_bonus(callback: CallbackQuery):
    parts = callback.data.split("_")
    ref_by = int(parts[1])
    new_user_id = int(parts[2])

    user = get_user(ref_by)
    if user and user[8] == 0:  # Если бонус ещё не выдан
        give_ref_bonus(ref_by)
        extend_subscription(ref_by, 1)
        
        try:
            await bot.send_message(
                ref_by,
                "Вам начислен +1 день к подписке за приглашённого пользователя!"
            )
        except:
            pass

        await callback.message.answer(
            f"Бонус выдан! Пользователю @{user[1]} добавлен +1 день."
        )
    else:
        await callback.answer("Бонус уже был выдан.", show_alert=True)

# ==================== ЗАПУСК ====================
async def main():
    print("=== ЗАПУСК БОТА ===")
    init_db()
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
