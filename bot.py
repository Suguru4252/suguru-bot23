import sqlite3
import datetime
import random
import string
import asyncio
import re
from zoneinfo import ZoneInfo
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ==================== КОНФИГ ====================
BOT_TOKEN = "8203822691:AAHriNfGaWY2ppCZ6bkEM5LpM_pprFyW8OM"
MOSCOW_TZ = ZoneInfo("Europe/Moscow")

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
            expired_notified INTEGER DEFAULT 0,
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
        "UPDATE users SET subscription_end = ?, has_active_sub = 1, expired_notified = 0 WHERE user_id = ?",
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
        cur.execute("UPDATE users SET subscription_end = ?, expired_notified = 0 WHERE user_id = ?", (new_end_str, user_id))
    else:
        new_end = datetime.datetime.now(MOSCOW_TZ) + datetime.timedelta(days=days)
        new_end_str = new_end.strftime("%Y-%m-%d %H:%M")
        cur.execute("UPDATE users SET subscription_end = ?, has_active_sub = 1, expired_notified = 0 WHERE user_id = ?", (new_end_str, user_id))
    conn.commit()
    conn.close()

def cancel_subscription(user_id):
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    cur.execute("UPDATE users SET subscription_end = NULL, has_active_sub = 0, expired_notified = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def mark_expired_notified(user_id):
    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    cur.execute("UPDATE users SET expired_notified = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

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
                    f"Новый пользователь!\n"
                    f"Ник: @{username}\n"
                    f"Имя: {first_name}\n"
                    f"Код: {code}"
                )
            except:
                pass

    await message.answer(
        f"Добро пожаловать в ChugurVPN!\n\n"
        f"ВНИМАНИЕ! Ваш персональный номер:\n"
        f"{code}\n\n"
        f"ЗАПОМНИТЕ ЕГО! Он нужен для подтверждения оплаты.\n\n"
        f"За первое посещение мы дарим вам 3 дня пробной подписки!\n\n"
        f"Для активации оплатите 1 рубль на реквизиты:\n"
        f"Банк: {PAYMENT_BANK}\n"
        f"Карта: {PAYMENT_CARD}\n\n"
        f"В сообщении перевода укажите ваш персональный номер: {code}",
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
                f"Новая оплата!\n"
                f"Персональный номер: {code}\n"
                f"Ник: @{callback.from_user.username}",
                reply_markup=admin_decision_keyboard(user_id)
            )
        except:
            pass

    await callback.answer("Платёж отправлен на модерацию. Ожидайте.", show_alert=True)

@router.callback_query(F.data == "pay_reject")
async def pay_reject(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("Когда созреете - приходите ещё, мы всегда рады!")

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
                f"Продление подписки!\n"
                f"Персональный номер: {code}\n"
                f"Ник: @{callback.from_user.username}\n"
                f"Сумма: 50 руб.",
                reply_markup=admin_decision_keyboard(user_id)
            )
        except:
            pass

    await callback.answer("Платёж на продление отправлен на модерацию.", show_alert=True)

@router.callback_query(F.data == "renew_reject")
async def renew_reject(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("Будем ждать вас снова!")

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
            "Добро пожаловать в админ-панель!\n\n"
            "Команды админа:\n"
            "/time - текущее время (МСК)\n"
            "/check_expired - проверка подписок"
        )
        await state.clear()
    else:
        await message.answer("Неверный пароль! Попробуйте ещё раз или нажмите /start для выхода.")

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

    now_msk = datetime.datetime.now(MOSCOW_TZ)
    await message.answer(
        f"Укажите дату истечения подписки в формате:\n"
        f"ДД:ММ:ГГГГ ЧЧ:ММ (по МСК)\n\n"
        f"Например: {now_msk.strftime('%d:%m:%Y %H:%M')}"
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
        # Парсим как московское время
        end_date_msk = datetime.datetime.strptime(message.text, "%d:%m:%Y %H:%M")
        end_date_msk = end_date_msk.replace(tzinfo=MOSCOW_TZ)
        # Сохраняем в базу в том же формате (строка)
        end_date_str = end_date_msk.strftime("%Y-%m-%d %H:%M")
    except Exception as e:
        await message.answer(f"Ошибка даты: {e}")
        return

    if user_id:
        activate_subscription(user_id, end_date_str)

        try:
            await bot.send_message(
                user_id,
                f"Подписка активирована!\n\n"
                f"{link}\n\n"
                f"Действует до: {end_date_msk.strftime('%d.%m.%Y %H:%M')} (МСК)"
            )
            await message.answer(f"Готово! Подписка активна до {end_date_msk.strftime('%d.%m.%Y %H:%M')} (МСК)")
        except:
            await message.answer("Не удалось отправить сообщение пользователю.")

    await state.clear()

# ==================== АДМИН: ОТКАЗ ====================
@router.callback_query(F.data.startswith("reject_"))
async def reject_payment(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[1])
    admin_temp_data[callback.from_user.id] = {"user_id": user_id}
    await callback.answer()
    await callback.message.answer("Напишите причину отказа:")
    await state.set_state(AdminRejectReason.waiting_for_reason)

@router.message(AdminRejectReason.waiting_for_reason)
async def send_reject(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    user_id = admin_temp_data.get(admin_id, {}).get("user_id")

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

# ==================== АДМИН: ИСТЕЧЕНИЕ ПОДПИСКИ ====================
@router.callback_query(F.data.startswith("take_"))
async def take_subscription(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    user = get_user(user_id)
    code = user[3]
    cancel_subscription(user_id)

    try:
        await bot.send_message(
            user_id,
            f"Подписка закончилась!\n\n"
            f"Чтобы продлить - оплатите 50 руб.:\n"
            f"Банк: {PAYMENT_BANK}\n"
            f"Карта: {PAYMENT_CARD}\n\n"
            f"В сообщении укажите ваш код: {code}",
            reply_markup=renew_menu_keyboard()
        )
        await callback.answer("Подписка забрана.", show_alert=True)
    except:
        await callback.answer("Ошибка отправки.", show_alert=True)

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

# ==================== КОМАНДЫ ====================
@router.message(Command("time"))
async def cmd_time(message: Message):
    now_msk = datetime.datetime.now(MOSCOW_TZ)
    await message.answer(
        f"Текущее время (МСК):\n"
        f"{now_msk.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"Формат для ввода: {now_msk.strftime('%d:%m:%Y %H:%M')}"
    )

@router.message(Command("check_expired"))
async def cmd_check_expired(message: Message):
    user = get_user(message.from_user.id)
    if not user or user[5] != 1:
        await message.answer("Нет доступа.")
        return

    conn = sqlite3.connect("vpn_bot.db")
    cur = conn.cursor()
    now_msk = datetime.datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M")
    
    cur.execute("SELECT user_id, personal_code, subscription_end, expired_notified, has_active_sub FROM users WHERE subscription_end IS NOT NULL")
    all_subs = cur.fetchall()
    conn.close()

    if not all_subs:
        await message.answer("Нет активных подписок.")
        return

    msg = f"Текущее время (МСК): {now_msk}\n\n"
    for sub in all_subs:
        msg += f"ID: {sub[0]}, Код: {sub[1]}, До: {sub[2]}, Увед: {sub[3]}, Актив: {sub[4]}\n"
    
    await message.answer(msg)

# ==================== ФОНОВАЯ ПРОВЕРКА (МСК) ====================
async def check_subscriptions():
    while True:
        try:
            now_msk = datetime.datetime.now(MOSCOW_TZ)
            now_str = now_msk.strftime("%Y-%m-%d %H:%M")
            
            admins = get_admins()
            if not admins:
                await asyncio.sleep(30)
                continue
                
            conn = sqlite3.connect("vpn_bot.db")
            cur = conn.cursor()
            
            # Ищем истекшие подписки (время сравнивается как строки, формат одинаковый)
            cur.execute(
                "SELECT user_id, personal_code, subscription_end FROM users WHERE has_active_sub = 1 AND subscription_end IS NOT NULL AND subscription_end <= ? AND expired_notified = 0",
                (now_str,)
            )
            expired = cur.fetchall()
            conn.close()

            if expired:
                print(f"[{now_str}] Найдено истекших подписок: {len(expired)}")
                
            for user_id, code, end_date in expired:
                print(f"[УВЕДОМЛЕНИЕ] Код {code} истек {end_date}, сейчас {now_str}")
                mark_expired_notified(user_id)
                
                for admin_id in admins:
                    try:
                        await bot.send_message(
                            admin_id,
                            f"Подписка истекла!\n"
                            f"Код: {code}\n"
                            f"ID: {user_id}\n"
                            f"Истекла: {end_date} (МСК)",
                            reply_markup=subscription_expired_keyboard(user_id)
                        )
                    except Exception as e:
                        print(f"Ошибка отправки админу {admin_id}: {e}")

        except Exception as e:
            print(f"Ошибка проверки: {e}")

        await asyncio.sleep(30)

# ==================== ЗАПУСК ====================
async def main():
    print("=== ЗАПУСК БОТА (МСК) ===")
    print(f"Текущее время: {datetime.datetime.now(MOSCOW_TZ).strftime('%d.%m.%Y %H:%M')}")
    init_db()
    dp.include_router(router)
    asyncio.create_task(check_subscriptions())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
