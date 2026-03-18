import logging
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import re

# 🔑 Настройки (вставь свои данные)
TOKEN = "8633962057:AAHURLKcS7fYytFzrCuQx4xPfynryYh8pKA"  # Получи у @BotFather в Telegram
API_URL = "https://flashcomapi.alwaysdata.net/api/generate-apk"  # Публичный API для сборки APK [citation:1]

# Включаем логирование
logging.basicConfig(level=logging.INFO)

# Инициализация бота
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Лимит: 3 сборки в день (как в оригинале) [citation:1]
user_builds = {}

# Машина состояний для сбора данных
class CreateApp(StatesGroup):
    name = State()
    package = State()
    url = State()
    icon = State()
    email = State()

# Функция проверки package name
def is_valid_package(package):
    return re.match(r'^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$', package) is not None

# Команда /start
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 **Добро пожаловать в APK Builder!**\n\n"
        "Я помогу тебе создать APK файл из твоего сайта.\n\n"
        "Нажми кнопку ниже, чтобы начать.",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="🚀 Создать APK", callback_data="create_app")]
            ]
        )
    )

# Кнопка "Создать APK"
@dp.callback_query(lambda c: c.data == "create_app")
async def process_create_app(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    today = asyncio.get_event_loop().time()
    
    # Проверка лимита (3 в день)
    if user_id in user_builds:
        if today - user_builds[user_id] < 86400:
            await callback.message.answer("❌ Ты уже использовал 3 сборки сегодня. Попробуй завтра.")
            return
    
    await callback.message.answer("📱 **Введи название приложения** (например: `Моя Игра`)")
    await state.set_state(CreateApp.name)
    await callback.answer()

# Шаг 1: Название
@dp.message(CreateApp.name)
async def get_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("📦 **Введи package name** (например: `com.example.game`)\n\nТолько латиница и точки.")
    await state.set_state(CreateApp.package)

# Шаг 2: Package name
@dp.message(CreateApp.package)
async def get_package(message: types.Message, state: FSMContext):
    if not is_valid_package(message.text):
        await message.answer("❌ Неверный формат. Используй например: `com.example.game`")
        return
    await state.update_data(package=message.text)
    await message.answer("🌐 **Введи URL твоего сайта** (https://)\n\nНапример: https://suguru4252.github.io/clicker-game/")
    await state.set_state(CreateApp.url)

# Шаг 3: URL
@dp.message(CreateApp.url)
async def get_url(message: types.Message, state: FSMContext):
    if not message.text.startswith("https://"):
        await message.answer("❌ Ссылка должна начинаться с https://")
        return
    await state.update_data(url=message.text)
    await message.answer(
        "🖼️ **Отправь ссылку на иконку** (прямую, например с хостинга картинок)\n"
        "Или отправь `/skip` чтобы пропустить."
    )
    await state.set_state(CreateApp.icon)

# Шаг 4: Иконка (пропуск)
@dp.message(CreateApp.icon, Command("skip"))
async def skip_icon(message: types.Message, state: FSMContext):
    await state.update_data(icon=None)
    await message.answer("📧 **Введи email** для уведомления о готовности:")
    await state.set_state(CreateApp.email)

# Шаг 4: Иконка (с картинкой)
@dp.message(CreateApp.icon)
async def get_icon(message: types.Message, state: FSMContext):
    if message.text and message.text.startswith("http"):
        await state.update_data(icon=message.text)
    else:
        await state.update_data(icon=None)
    await message.answer("📧 **Введи email** для уведомления о готовности:")
    await state.set_state(CreateApp.email)

# Шаг 5: Email и финальная отправка
@dp.message(CreateApp.email)
async def get_email(message: types.Message, state: FSMContext):
    if "@" not in message.text:
        await message.answer("❌ Введи корректный email")
        return
    
    data = await state.get_data()
    user_id = message.from_user.id
    
    # Отправка в API [citation:1]
    loading_msg = await message.answer("🔄 Собираю APK, подожди немного...")
    
    async with aiohttp.ClientSession() as session:
        payload = {
            "name": data['name'],
            "package_name": data['package'],
            "url": data['url'],
            "email": message.text,
            "icon_url": data.get('icon')
        }
        
        try:
            async with session.post(API_URL, json=payload) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    download_link = result.get('download_link')
                    
                    if download_link:
                        await loading_msg.delete()
                        await message.answer(
                            f"✅ **Готово!**\n\n"
                            f"📱 Название: {data['name']}\n"
                            f"📦 Package: {data['package']}\n"
                            f"🌐 Сайт: {data['url']}\n\n"
                            f"🔗 **Скачать APK:** [Нажми сюда]({download_link})",
                            disable_web_page_preview=True
                        )
                        
                        # Обновляем лимит пользователя
                        user_builds[user_id] = asyncio.get_event_loop().time()
                    else:
                        await loading_msg.edit_text("❌ Ошибка при сборке. Попробуй позже.")
                else:
                    await loading_msg.edit_text(f"❌ Ошибка API (код {resp.status})")
        except Exception as e:
            await loading_msg.edit_text(f"❌ Ошибка соединения: {e}")
    
    await state.clear()

# Запуск
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
