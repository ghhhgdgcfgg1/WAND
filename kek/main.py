import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from rsq import token
from data import perfumes
from aiogram.types import FSInputFile
from aiogram.types import BotCommand, MenuButtonCommands
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    FSInputFile,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InputMediaPhoto,
    MenuButtonDefault
)
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import Message
from aiogram.types import MenuButtonDefault
from aiogram.types import URLInputFile
from PIL import Image, ImageOps, ImageDraw, ImageFilter
import io
import json
import requests
from aiogram import Router
import aiohttp
from aiogram.exceptions import TelegramBadRequest
router = Router()
from pathlib import Path
from io import BytesIO
from aiogram.types import BufferedInputFile
ADMIN_IDS = {1418123274}
BASE_DIR = Path(__file__).resolve().parent
PHOTOS_DIR = BASE_DIR / "photos"
CACHE_DIR = BASE_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)
#PHOTOS_DIR = BASE_DIR / "photos"
#import requests
FLASK_URL = "https://aromaid.ru"
user_favorites = {}
import os
from aiogram.types import FSInputFile, URLInputFile

NO_IMAGE_PATH = PHOTOS_DIR / "no_image.jpg"

def get_photo_input(perfume: dict):
    raw = perfume.get("photo_url") or perfume.get("photo")
    url = normalize_photo_url(raw)

    if not url:
        return FSInputFile(NO_IMAGE_PATH)

    return URLInputFile(url)
async def fetch_perfumes():
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{FLASK_URL}/api/products") as resp:
            resp.raise_for_status()
            return await resp.json()
async def safe_edit_text(message, text, reply_markup=None, parse_mode="HTML"):
    try:
        await message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    except TelegramBadRequest as e:
        # сообщение без текста
        if "there is no text in the message" in str(e):
            await message.answer(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        # текст тот же самый — просто игнорируем
        elif "message is not modified" in str(e):
            pass
        else:
            raise

async def track(telegram_id, event, value="", username=None):
    payload = {
        "telegram_id": telegram_id,
        "event": event,
        "value": value
    }
    if username:
        payload["username"] = username

    async with aiohttp.ClientSession() as session:
        try:
            await session.post(f"{FLASK_URL}/api/track", json=payload)
        except Exception as e:
            print(f"Track error: {e}")
def auth_user(message):
    payload = {
        "telegram_id": message.from_user.id,
        "username": message.from_user.username
    }

    r = requests.post(f"{FLASK_URL}/api/telegram/auth", json=payload)
    r.raise_for_status()
    user_id = r.json()["user_id"]

    return user_id

def normalize_photo_url(photo: str | None) -> str | None:
    if not photo:
        return None

    photo = str(photo).strip()

    # если уже правильный домен
    if photo.startswith("https://aromaid.ru/"):
        return photo

    # если cloudflare tunnel — вырезаем filename и строим нормальный URL
    if "trycloudflare.com" in photo and "/uploads/" in photo:
        filename = photo.split("/uploads/", 1)[1]
        return f"{FLASK_URL}/uploads/{filename}"

    # если просто имя файла
    if not photo.startswith(("http://", "https://")):
        return f"{FLASK_URL}/uploads/{photo}"

    # любой другой http(s) оставляем как есть
    return photo
def get_user_cards(telegram_id):
    r = requests.get(f"{FLASK_URL}/api/cards/{telegram_id}")
    r.raise_for_status()
    return r.json()

def load_cards(telegram_id):
    r = requests.get(f"{FLASK_URL}/api/cards/{telegram_id}", timeout=10)
    r.raise_for_status()
    return r.json()
"""
SEARCH_FILTERS = {
    "volumes": ["30 мл", "50 мл", "100 мл", "200 мл"],
    "notes": ["цитрус", "цветочные", "древесные", "восточные", 
              "фруктовые", "мускус", "амбра", "ваниль", "пряные"]
}
"""
def add_card(telegram_id, product_id):
    r = requests.post(
        f"{FLASK_URL}/api/card/add/telegram",
        json={
            "telegram_id": telegram_id,
            "product_id": product_id
        }
    )
    r.raise_for_status()


ITEMS_PER_PAGE = 5
bot = Bot(token=token)
dp = Dispatcher()

# Новые состояния для разных типов поиска
class SearchState(StatesGroup):
    waiting_query = State()
    waiting_note = State()
    waiting_brand = State()
    browsing = State()

async def resize_photo(photo_path: str, max_size: tuple = (1000, 1000), 
                      border_radius: int = 20, shadow_offset: int = 5) -> FSInputFile:
    """
    Создает фото со стильной рамкой как на примере
    max_size: (ширина, высота) в пикселях
    border_radius: радиус скругления углов
    shadow_offset: смещение тени
    """
    full_path = BASE_DIR / photo_path
    # Открываем изображение
    #photo_path
    photo_name = Path(photo_path).stem
    cache_path = CACHE_DIR / f"{photo_name}_{max_size[0]}.jpg"

    # ✅ ЕСЛИ УЖЕ ЕСТЬ — СРАЗУ ОТДАЁМ
    if cache_path.exists():
        return FSInputFile(cache_path)
    with Image.open(full_path) as img:
        # Конвертируем RGBA в RGB если нужно
        if img.mode in ('RGBA', 'LA', 'P'):
            # Создаем белый фон для прозрачных изображений
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'RGBA':
                background.paste(img, mask=img.split()[3])
            else:
                background.paste(img)
            img = background
        
        # Сохраняем оригинальные пропорции
        original_width, original_height = img.size
        
        # Вычисляем новые размеры с сохранением пропорций
        ratio = min(max_size[0] / original_width, max_size[1] / original_height)
        new_width = int(original_width * ratio)
        new_height = int(original_height * ratio)
        
        # Изменяем размер
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Создаем маску для скругленных углов
        mask = Image.new('L', (new_width, new_height), 0)
        draw = ImageDraw.Draw(mask)
        
        # Рисуем скругленный прямоугольник
        draw.rounded_rectangle(
            [(0, 0), (new_width, new_height)],
            radius=border_radius,
            fill=255
        )
        
        # Применяем маску к изображению
        img.putalpha(mask)
        
        # Создаем изображение с тенью (большего размера)
        shadow_size = (new_width + shadow_offset * 2, new_height + shadow_offset * 2)
        shadow_img = Image.new('RGBA', shadow_size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_img)
        
        # Рисуем тень (темный прямоугольник со скругленными углами)
        shadow_draw.rounded_rectangle(
            [(shadow_offset, shadow_offset), 
             (new_width + shadow_offset, new_height + shadow_offset)],
            radius=border_radius,
            fill=(50, 50, 50, 150)  # Полупрозрачный темный цвет
        )
        
        # Немного размываем тень для мягкости
        shadow_img = shadow_img.filter(ImageFilter.GaussianBlur(radius=3))
        
        # Создаем финальное изображение
        final_img = Image.new('RGBA', shadow_size, (255, 255, 255, 0))
        
        # Накладываем тень
        final_img.paste(shadow_img, (0, 0), shadow_img)
        
        # Накладываем основное изображение поверх тени
        main_img_position = (
            (shadow_size[0] - new_width) // 2,
            (shadow_size[1] - new_height) // 2
        )
        final_img.paste(img, main_img_position, img)
        
        # Сохраняем во временный файл
        temp_path = f"temp_{photo_path.split('/')[-1]}"
        final_img.save(temp_path, "PNG", quality=95, optimize=True)
        
        return FSInputFile(temp_path)
def order_keyboard(source: str, index: int,perfume_id: int):
    kb = InlineKeyboardBuilder()

    kb.button(
        text="📱 Сделать заказ",
        callback_data=f"order_info:{perfume_id}"
    )

    kb.button(
        text="⬅️ Назад",
        callback_data=f"order_back:{source}:{index}"
    )

    kb.adjust(1)
    return kb.as_markup()
async def url_to_telegram_file(url: str, filename="photo.jpg"):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, allow_redirects=True) as r:
            r.raise_for_status()
            data = await r.read()
            return BufferedInputFile(data, filename=filename)
@dp.callback_query(F.data.startswith("order_back:"))
async def order_back(callback: CallbackQuery, state: FSMContext):
    _, source, index = callback.data.split(":")
    index = int(index)
    
    # Удаляем старое фото (фото подробного описания) если есть
    data = await state.get_data()
    old_photo_id = data.get("order_photo_id")
    if old_photo_id:
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=old_photo_id
            )
        except:
            pass
        await state.update_data(order_photo_id=None)
    
    # Удаляем сообщение с описанием и кнопкой "Назад"
    try:
        await callback.message.delete()
    except:
        pass

    # Получаем ID оригинальной карточки, которую нужно восстановить
    original_card_id = data.get("original_card_id")

    # --- ЛОГИКА ДЛЯ РАЗНЫХ РАЗДЕЛОВ ---
    
    if source == "catalog":
        perfume = perfumes[index]
        markup = catalog_card_keyboard(index, callback.from_user.id)
        """
        framed_photo = await resize_photo(perfume["photo"], 
                                         border_radius=20, 
                                         shadow_offset=4)
        """
        framed_photo = get_photo_input(perfume)
        caption = (
            f"<b>{perfume['name']}</b>\n"
            f"Пол: {perfume['category']}\n"
            f"Объём: {perfume['volume']}\n"
        )
        
        if original_card_id:
            try:
                await callback.bot.edit_message_media(
                    chat_id=callback.message.chat.id,
                    message_id=original_card_id,
                    media=InputMediaPhoto(
                        media=framed_photo,
                        caption=caption,
                        parse_mode="HTML"
                    ),
                    reply_markup=markup
                )
            except TelegramBadRequest as e:
                # ИСПРАВЛЕНИЕ: Если сообщение не изменилось, ничего не делаем (не дублируем)
                if "message is not modified" in str(e):
                    pass
                else:
                    # Если другая ошибка (например, сообщение удалено), отправляем новое
                    await callback.message.answer_photo(
                        photo=framed_photo, caption=caption, reply_markup=markup, parse_mode="HTML"
                    )
            except Exception:
                # Общая ошибка - отправляем новое
                await callback.message.answer_photo(
                    photo=framed_photo, caption=caption, reply_markup=markup, parse_mode="HTML"
                )
        else:
            await callback.message.answer_photo(
                photo=framed_photo, caption=caption, reply_markup=markup, parse_mode="HTML"
            )
        
    elif source == "category":
        items = data.get("cat_items", [])
        perfume = items[index]
        prefix = data.get("back_prefix", "gender")
        
        categories = []
        category2 = perfume.get("category2", [])
        if isinstance(category2, str):
            categories = [category2]
        elif isinstance(category2, list):
            categories = category2
        else:
            categories = [perfume.get("category", "не указано")]
        
        categories_text = ", ".join(categories) if isinstance(categories, list) else str(categories)
        caption = (
            f"<b>{perfume['name']}</b>\n"
            f"Пол: {categories_text}\n"
            f"Объём: {perfume.get('volume', 'не указано')}"
        )
        
        markup = category_card_keyboard(index, len(items), prefix, perfume, callback.from_user.id)
        """
        framed_photo = await resize_photo(
            perfume["photo"], 
            max_size=(800, 800), 
            border_radius=20, 
            shadow_offset=8
        )
        """
        framed_photo = get_photo_input(perfume)
        if original_card_id:
            try:
                await callback.bot.edit_message_media(
                    chat_id=callback.message.chat.id,
                    message_id=original_card_id,
                    media=InputMediaPhoto(
                        media=framed_photo,
                        caption=caption,
                        parse_mode="HTML"
                    ),
                    reply_markup=markup
                )
            except TelegramBadRequest as e:
                # ИСПРАВЛЕНИЕ
                if "message is not modified" in str(e):
                    pass
                else:
                    await callback.message.answer_photo(
                        photo=framed_photo, caption=caption, reply_markup=markup, parse_mode="HTML"
                    )
            except Exception:
                await callback.message.answer_photo(
                    photo=framed_photo, caption=caption, reply_markup=markup, parse_mode="HTML"
                )
        else:
            await callback.message.answer_photo(
                photo=framed_photo, caption=caption, reply_markup=markup, parse_mode="HTML"
            )
        
    elif source == "search":
        results = data.get("search_results", [])
        perfume = results[index]
        
        caption = (
            f"<b>{perfume['name']}</b>\n"
            f"Пол: {perfume.get('category', 'не указано')}\n"
            f"Объём: {perfume.get('volume', 'не указано')}"
        )
        
        markup = search_card_keyboard(index, len(results), callback.from_user.id, perfume)
        """
        framed_photo = await resize_photo(perfume["photo"], 
                                         max_size=(800, 800), 
                                         border_radius=20, 
                                         shadow_offset=8)
        """
        framed_photo = get_photo_input(perfume)
        if original_card_id:
            try:
                await callback.bot.edit_message_media(
                    chat_id=callback.message.chat.id,
                    message_id=original_card_id,
                    media=InputMediaPhoto(
                        media=framed_photo,
                        caption=caption,
                        parse_mode="HTML"
                    ),
                    reply_markup=markup
                )
            except TelegramBadRequest as e:
                # ИСПРАВЛЕНИЕ
                if "message is not modified" in str(e):
                    pass
                else:
                    await callback.message.answer_photo(
                        photo=framed_photo, caption=caption, reply_markup=markup, parse_mode="HTML"
                    )
            except Exception:
                await callback.message.answer_photo(
                    photo=framed_photo, caption=caption, reply_markup=markup, parse_mode="HTML"
                )
        else:
            await callback.message.answer_photo(
                photo=framed_photo, caption=caption, reply_markup=markup, parse_mode="HTML"
            )
    
    else:
        await callback.answer("Ошибка возврата")
        return
    
    await callback.answer()
@dp.message(Command("reload"))
async def reload_catalog(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Нет доступа")
        return

    global perfumes
    perfumes = await fetch_perfumes()
    await message.answer(f"Каталог обновлён. Товаров: {len(perfumes)}")

async def order_click_api(telegram_id: int, product_id: int, username: str | None = None):
    async with aiohttp.ClientSession() as session:
        await session.post(
            f"{FLASK_URL}/api/orders/click",
            json={"telegram_id": telegram_id, "product_id": product_id, "username": username}
        )

@dp.callback_query(F.data.startswith("order_info:"))
async def order_info(callback: CallbackQuery):
    perfume_id = int(callback.data.split(":")[1])
    
    username = callback.from_user.username
    if username:
        username = f"@{username}"
    else:
        username = callback.from_user.first_name

    await track(callback.from_user.id, "order_click", perfume_id)
    await order_click_api(callback.from_user.id, perfume_id, username=username)
    kb = InlineKeyboardBuilder()
    kb.button(
        text="⬅️ Назад",
        callback_data="order_back_to_description"
    )
    kb.adjust(1)

    await callback.message.answer(
        """<u>Для оформления заказа обратитесь к человеку</u> который <b>пригласил Вас в чат</b> -  https://t.me/aromo_code

Или напишите Нашим администраторам

Лидия - @LidiyaKlimenteva
Николай - @Naum_SW

Арома гороскоп в подарок каждому участнику чата по запросу.

<b>🎁 При покупке двух и более ароматов подарок.</b> Расчет натальной карты и <u>ответы на 5 ключевых вопросов</u>
https://t.me/aromo_code
пишите <b>'хочу разбор'</b>

Наша компания международная и охватывает почти все страны мира. Офисы компании присутствуют в большинстве городов России и во всех странах СНГ. Доставка от компании возможна почти по всей России (уточняйте у администраторов). По Москве, Санкт-Петербургу и другим крупным городам России возможна курьерская доставка день в день.""",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

    await callback.answer()

@dp.callback_query(F.data == "order_back_to_description")
async def order_back_to_description(callback: CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    # НИЧЕГО не пересоздаём
    # описание уже есть
    await callback.answer()



@dp.callback_query(F.data.startswith("back_to_search_"))
async def back_to_search(callback: CallbackQuery, state: FSMContext):
    try:
        index = int(callback.data.replace("back_to_search_", ""))
    except ValueError:
        await callback.answer("Ошибка в данных")
        return
    
    data = await state.get_data()
    results = data.get("search_results", [])
    
    if not results or index >= len(results):
        await callback.answer("Результаты поиска не найдены")
        return
    
    await state.update_data(search_index=index)
    perfume = results[index]
    """
    # Используем фото со стильной рамкой
    framed_photo = await resize_photo(perfume["photo"], 
                                     max_size=(800, 800), 
                                     border_radius=20, 
                                     shadow_offset=8)
    """
    framed_photo = get_photo_input(perfume)
    # Формируем заголовок
    search_type = data.get("search_type", "поиска")
    caption = (
        f"<b>{perfume['name']}</b>\n"
        f"Пол: {perfume.get('category', 'не указано')}\n"
        f"Объём: {perfume.get('volume', 'не указано')}\n"
    )
    """
    if search_type == "note":
        caption += f"<i>Найдено по ноте: {data.get('search_query', '')}</i>"
    """
    if search_type == "":
        caption += f"<i>Найдено по бренду: {data.get('search_query', '')}</i>"
    # Редактируем сообщение с товаром
    try:
        await callback.message.edit_media(
            media=InputMediaPhoto(
                media=framed_photo,
                caption=caption,
                parse_mode="HTML"
            ),
            reply_markup=search_card_keyboard(index, len(results))
        )
    except:
        # Если нельзя редактировать, отправляем новое
        await callback.message.answer_photo(
            photo=framed_photo,
            caption=caption,
            reply_markup=search_card_keyboard(index, len(results)),
            parse_mode="HTML"
        )
    
    await callback.answer()

@dp.callback_query(F.data.startswith("back_to_category_"))
async def back_to_category(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    
    if len(parts) < 5:  # back_to_category_type_index
        await callback.answer("Ошибка в данных")
        return
    
    category_type = parts[3]
    category_index = int(parts[4])
    
    data = await state.get_data()
    items = data.get("cat_items", [])
    
    if not items or category_index >= len(items):
        await callback.answer("Категория не найдена")
        return
    
    perfume = items[category_index]
    
    # Обновляем состояние
    await state.update_data(cat_index=category_index)
    
    # Формируем список категорий для отображения
    categories = []
    category2 = perfume.get("category2", [])
    
    if isinstance(category2, str):
        categories = [category2]
    elif isinstance(category2, list):
        categories = category2
    elif not category2:
        categories = [perfume.get("category", "не указано")]
    
    # Формируем текст категорий
    if isinstance(categories, list) and len(categories) > 0:
        categories_text = ", ".join(categories)
    else:
        categories_text = str(categories)
    
    caption = (
        f"<b>{perfume['name']}</b>\n"
        f"Пол: {categories_text}\n"
        f"Объём: {perfume.get('volume', 'не указано')}"
    )
    """"
    # Используем фото со стильной рамкой
    framed_photo = await resize_photo(
        perfume["photo"], 
        max_size=(800, 800), 
        border_radius=20, 
        shadow_offset=8
    )
    """
    framed_photo = get_photo_input(perfume)
    # Редактируем сообщение с товаром
    try:
        await callback.message.edit_media(
            media=InputMediaPhoto(
                media=framed_photo,
                caption=caption,
                parse_mode="HTML"
            ),
            reply_markup=category_card_keyboard(category_index, len(items), category_type, perfume)
        )
    except:
        # Если нельзя редактировать, отправляем новое
        await callback.message.answer_photo(
            photo=framed_photo,
            caption=caption,
            reply_markup=category_card_keyboard(category_index, len(items), category_type, perfume),
            parse_mode="HTML"
        )
    
    await callback.answer()
    
def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📦 Посмотреть весь каталог")
            ],
            [
                KeyboardButton(text="📂 Категории"),
                KeyboardButton(text="🔍 Поиск")
            ],
            [
                KeyboardButton(text="⭐ Избранное"),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие"
    )


def favorite_button(telegram_id: int,perfume_id: int,source: str,index: int):
    user_favs = user_favorites.get(telegram_id, set())

    if perfume_id in user_favs:
        return (
            "❌ Удалить из избранного",
            f"fav_remove:{perfume_id}:{source}:{index}"
        )
    else:
        return (
            "⭐ Добавить в избранное",
            f"fav_add:{perfume_id}:{source}:{index}"
        )





def categories_keyboard():
    kb = InlineKeyboardBuilder()

    kb.button(text="👩 Для неё", callback_data="cat_gender_women")
    kb.button(text="👨 Для него", callback_data="cat_gender_men")
    kb.button(text="⚧ Унисекс", callback_data="cat_gender_unisex")

    kb.button(text="✨ Нишевые", callback_data="cat_scent_niche")
    kb.button(text="🌸 Цветочные", callback_data="cat_scent_floral")
    kb.button(text="🍋 Цитрусовые", callback_data="cat_scent_citrus")
    kb.button(text="🌳 Древесные", callback_data="cat_scent_woody")
    kb.button(text="🔥 Восточные", callback_data="cat_scent_oriental")
    kb.button(text="🍓 Фруктовые", callback_data="cat_scent_fruity")

    kb.adjust(2, 1, 1, 2, 2)
    return kb.as_markup()

# Клавиатура для выбора типа поиска

def favorites_keyboard(index: int, total: int, uid: int):
    items = [p for p in perfumes if p["id"] in user_favorites.get(uid, set())]
    perfume = items[index]

    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️", callback_data=f"fav_prev_{index}")
    kb.button(text=f"{index+1}/{total}", callback_data="noop")
    kb.button(text="➡️", callback_data=f"fav_next_{index}")
    kb.button(text="❌ Удалить", callback_data=f"fav_remove:{perfume['id']}:favorites:{index}")
    kb.adjust(3, 1)

    return kb.as_markup()

@dp.callback_query(F.data.regexp(r"^fav_(prev|next)_\d+$"))
async def fav_navigation(callback: CallbackQuery):
    uid = callback.from_user.id
    action, index = callback.data.split("_")[1:]
    index = int(index)

    items = [p for p in perfumes if p["id"] in user_favorites.get(uid, set())]

    if not items:
        await callback.answer()
        return

    if action == "next" and index < len(items) - 1:
        index += 1
    elif action == "prev" and index > 0:
        index -= 1

    perfume = items[index]
    """
    # ✅ используем тот же ресайз, что и в "Избранном"
    framed_photo = await resize_photo(perfume["photo"])
    """
    framed_photo = get_photo_input(perfume)
    caption = (
        f"<b>{perfume['name']}</b>\n"
        f"Пол: {perfume.get('category','не указано')}\n"
        f"Объём: {perfume.get('volume','не указано')}"
    )

    try:
        await callback.message.edit_media(
            media=InputMediaPhoto(
                media=framed_photo,
                caption=caption,
                parse_mode="HTML"
            ),
            reply_markup=favorites_keyboard(index, len(items), uid)
        )
    except TelegramBadRequest:
        # если нельзя отредактировать — отправим новое
        await callback.message.answer_photo(
            photo=framed_photo,
            caption=caption,
            reply_markup=favorites_keyboard(index, len(items), uid),
            parse_mode="HTML"
        )

    await callback.answer()


@dp.message(F.text == "⭐ Избранное")
async def show_favorites(message: Message, state: FSMContext):
    await state.clear()
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
    await track(message.from_user.id, "open_favorites", username=username)
    uid = message.from_user.id
    fav_ids = list(user_favorites.get(uid, set()))

    if not fav_ids:
        await message.answer("😔 У вас пока нет избранных ароматов")
        return

    index = 0
    perfume = next(p for p in perfumes if p["id"] == fav_ids[index])
    """
    framed_photo = await resize_photo(perfume["photo"])
    """
    framed_photo = get_photo_input(perfume)
    caption = (
        f"<b>{perfume['name']}</b>\n"
        f"Пол: {perfume['category']}\n"
        f"Объём: {perfume['volume']}"
    )

    await message.answer_photo(
        photo=framed_photo,
        caption=caption,
        reply_markup=favorites_keyboard(index, len(fav_ids), uid),
        parse_mode="HTML"
    )

async def fav_add_api(telegram_id: int, product_id: int, username: str | None = None):
    async with aiohttp.ClientSession() as session:
        await session.post(
            f"{FLASK_URL}/api/favorites/add",
            json={"telegram_id": telegram_id, "product_id": product_id, "username": username}
        )

async def fav_remove_api(telegram_id: int, product_id: int):
    async with aiohttp.ClientSession() as session:
        await session.post(
            f"{FLASK_URL}/api/favorites/remove",
            json={"telegram_id": telegram_id, "product_id": product_id}
        )

@dp.callback_query(F.data.startswith("fav_add:"))
async def fav_add(callback: CallbackQuery, state: FSMContext):
    _, perfume_id, source, index = callback.data.split(":")
    perfume_id = int(perfume_id)
    index = int(index)
    uid = callback.from_user.id

    user_favorites.setdefault(uid, set()).add(perfume_id)
    username = callback.from_user.username
    if username:
        username = f"@{username}"
    else:
        username = callback.from_user.first_name
    await fav_add_api(uid, perfume_id, username=username)
    await track(uid, "fav_add", perfume_id)
    await update_fav_keyboard(callback, state, source, index, uid)
    await callback.answer("⭐ Добавлено в избранное")

async def fetch_favorites(telegram_id: int):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{FLASK_URL}/api/favorites/{telegram_id}") as resp:
            resp.raise_for_status()
            return await resp.json()

@dp.callback_query(F.data.startswith("fav_remove:"))
async def fav_remove(callback: CallbackQuery, state: FSMContext):
    _, perfume_id, source, index = callback.data.split(":")
    perfume_id = int(perfume_id)
    index = int(index)
    uid = callback.from_user.id

    user_favorites.get(uid, set()).discard(perfume_id)
    await fav_remove_api(uid, perfume_id)
    await track(uid, "fav_remove", perfume_id)
    # если удаляем из раздела "Избранное"
    if source == "favorites":
        items = [p for p in perfumes if p["id"] in user_favorites.get(uid, set())]

        if not items:
            await callback.message.delete()
            await callback.message.answer(
        "😔 У вас больше нет избранных ароматов"
    )
            await callback.answer("Избранное пусто")
            return

        index = min(index, len(items) - 1)
        perfume = items[index]
        """
        framed_photo = await resize_photo(perfume["photo"])
        """
        framed_photo = get_photo_input(perfume)
        await callback.message.edit_media(
            media=InputMediaPhoto(
                media=framed_photo,
                caption=f"<b>{perfume['name']}</b>",
                parse_mode="HTML"
            ),
            reply_markup=favorites_keyboard(index, len(items), uid)
        )

        await callback.answer("❌ Удалено из избранного")
        return

    # остальные источники (catalog / search / category)
    await update_fav_keyboard(callback, state, source, index, uid)
    await callback.answer("❌ Удалено из избранного")



async def safe_edit_text(message, text, reply_markup):
    try:
        await message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


async def update_fav_keyboard(callback, state: FSMContext, source, index, uid):
    if source == "catalog":
        markup = catalog_card_keyboard(index, uid)

    elif source == "category":
        data = await state.get_data()
        items = data.get("cat_items", [])
        prefix = data.get("back_prefix", "gender")

        markup = category_card_keyboard(
            index,
            len(items),
            prefix,
            items[index],
            uid
        )

    elif source == "search":
        data = await state.get_data()
        results = data.get("search_results", [])

        markup = search_card_keyboard(
            index,
            len(results),
            uid,
            results[index]
        )

    else:
        return

    await callback.message.edit_reply_markup(reply_markup=markup)


@dp.message(F.text == "📦 Посмотреть весь каталог")
async def catalog_start(message: Message, state: FSMContext):
    await state.clear()
    await track(message.from_user.id, "open_catalog", username=(
    f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
))
    perfume = perfumes[0]
    photo = get_photo_input(perfume)

    caption = (
        f"<b>{perfume['name']}</b>\n"
        f"Пол: {perfume['category']}\n"
        f"Объём: {perfume['volume']}\n"
    )

    await message.answer_photo(
        photo=photo,
        caption=caption,
        reply_markup=catalog_card_keyboard(0, message.from_user.id),
        parse_mode="HTML"
    )

def back_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data="back")
    return kb.as_markup()

# Функции поиска
def search_perfumes(query: str):
    query = query.lower()
    results = []

    for p in perfumes:
        fields = []

        # название
        fields.append(p.get("name", ""))

        # бренд
        fields.append(p.get("brand2", ""))
        fields.append(p.get("brand", ""))
        # ноты
        """
        notes = p.get("notes", [])
        if isinstance(notes, list):
            fields.extend(notes)
        elif isinstance(notes, str):
            fields.append(notes)
        """
        # категория аромата
        scent = p.get("scent_category", [])
        if isinstance(scent, list):
            fields.extend(scent)
        elif isinstance(scent, str):
            fields.append(scent)

        # проверка совпадения
        if any(query in str(field).lower() for field in fields):
            results.append(p)

    return results


def search_card_keyboard(index: int, total: int, telegram_id: int, perfume):
    
    fav_text, fav_cb = favorite_button(telegram_id,perfume["id"],source="search",index=index)

    kb = InlineKeyboardBuilder()

    kb.button(text="⬅️", callback_data=f"search_prev_{index}")
    kb.button(text=f"{index+1}/{total}", callback_data="noop")
    kb.button(text="➡️", callback_data=f"search_next_{index}")

    kb.button(
    text="ℹ️ Подробнее",callback_data=f"search_open_{index}")
    kb.button(text=fav_text, callback_data=fav_cb)

    kb.adjust(3, 1, 1)
    return kb.as_markup()


@dp.message(F.text == "/start")
async def start(message: Message, state: FSMContext):
    await state.clear()
    username = message.from_user.username
    if not username:
        username = message.from_user.first_name
    else:
        username = f"@{username}"
    await track(message.from_user.id, "bot_start", username=username)
    text = """🌸 <b>Добро пожаловать в мир изысканных ароматов!</b> 🌸
Вы любите качественный парфюм, но не готовы переплачивать? У Нас — идеальное решение: премиальные ароматы, но по приятной цене. А также нишевая линейка ароматов от известного бренда.

<b>Почему Наши ароматы — Ваш лучший выбор?</b>
Ароматы созданы известными парфюмерами по мотивам известных брендов. Тот же характер, те же ноты, тот же шарм.

<b>Качественный состав</b> — используем проверенные парфюмерные компоненты, безопасные и стойкие.
Имеются все сертификаты качества и "честный знак".

<b>Отличная стойкость</b> — ароматы держат положенное время и более, не теряя глубины и шлейфа.

<b>Доступная цена!</b> Мы отказались от дорогостоящей коммерческой рекламы, для того чтобы Вы могли  экономить до 90 % по сравнению с ценами на люксовые бренды.
<b>Отличный шанс обрести роскошный парфюм без переплат!</b>

Ниже для Вас доступен просмотр всего каталога - более 50ти ароматов; категории ароматов и поиск по совпадению слов."""
    #user_id = auth_user(message)
    #await track(message.from_user.id, "bot_start")
    await message.answer(
        text,
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "back_to_start")
async def back_to_start(callback: CallbackQuery):
    text = """🌸 <b>Добро пожаловать в мир изысканных ароматов!</b> 🌸
Вы любите качественный парфюм, но не готовы переплачивать? У Нас — идеальное решение: премиальные ароматы, но по приятной цене. А также нишевая линейка ароматов от известного бренда.

<b>Почему Наши ароматы — Ваш лучший выбор?</b>
Ароматы созданы известными парфюмерами по мотивам известных брендов. Тот же характер, те же ноты, тот же шарм.

<b>Качественный состав</b> — используем проверенные парфюмерные компоненты, безопасные и стойкие.
Имеются все сертификаты качества и "честный знак".

<b>Отличная стойкость</b> — ароматы держат положенное время и более, не теряя глубины и шлейфа.

<b>Доступная цена!</b> Мы отказались от дорогостоящей коммерческой рекламы, для того чтобы Вы могли  экономить до 90 % по сравнению с ценами на люксовые бренды.
<b>Отличный шанс обрести роскошный парфюм без переплат!</b>

Ниже для Вас доступен просмотр всего каталога - более 50ти ароматов; категории ароматов и поиск по совпадению слов."""
    
    await callback.message.answer(
        text,
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(Command("catalog"))
async def catalog_command(message: Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder()
    for p in perfumes:
        kb.button(text=p["name"], callback_data=f"perf_{p['id']}")
    kb.adjust(1)

    await message.answer(
        "📦 <b>Весь каталог:</b>",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )



@dp.message(Command("categories"))
async def show_categories_command(message: Message, state: FSMContext):
    await message.answer(
        "📂 В данном разделе Вы сможете выбрать нужную категорию ароматов:",
        reply_markup=categories_keyboard()
    )

# Обработчики выбора типа поиска
def normalize_gender(value: str) -> str:
    v = value.lower()
    if any(x in v for x in ["жен", "для неё", "female", "women"]):
        return "для неё"
    if any(x in v for x in ["муж", "для него", "male", "men"]):
        return "для него"
    if any(x in v for x in ["уни", "unisex"]):
        return "унисекс"
    return ""
@dp.callback_query(F.data.startswith("cat_gender_"))
async def show_gender_category_handler(callback: CallbackQuery, state: FSMContext):
    gender_type = callback.data.replace("cat_gender_", "")
    
    # Маппинг callback-данных на значения категорий
    gender_map = {
        "women": "для неё",
        "men": "для него", 
        "unisex": "унисекс"
    }
    
    target_gender = gender_map.get(gender_type)
    if not target_gender:
        await callback.answer("Неизвестная категория")
        return
    
    # Фильтрация по category2 (списку категорий)
    items = []
    for p in perfumes:
        raw = p.get("category2") or p.get("category") or ""
        gender = normalize_gender(raw)
        if gender == target_gender:
            items.append(p)
    if not items:
        await callback.message.answer("😔 В этой категории пока нет товаров")
        print("DEBUG category:", target_gender)
        print("DEBUG found:", len(items))
        print("DEBUG example product:", perfumes[0])
        await callback.answer()
        return
    
    await state.update_data(
        cat_items=items,
        cat_index=0,
        cat_type="gender"
    )
    
    perfume = items[0]
    
    # Формируем список категорий для отображения
    categories = []
    category2 = perfume.get("category2", [])
    
    if isinstance(category2, str):
        categories = [category2]  # Превращаем строку в список
    elif isinstance(category2, list):
        categories = category2
    elif not category2:
        categories = [perfume.get("category", "не указано")]
    
    # ФИКС: Проверяем, что categories действительно список
    print(f"DEBUG: categories type = {type(categories)}, value = {categories}")
    
    # Добавляем информацию о поле и объеме
    if isinstance(categories, list) and len(categories) > 0:
        # Если это список, соединяем элементы через запятую
        categories_text = ", ".join(categories)
    else:
        # Если по какой-то причине не список, просто выводим как есть
        categories_text = str(categories)
    
    caption = (
        f"<b>{perfume['name']}</b>\n"
        f"Пол: {categories_text}\n"
        f"Объём: {perfume.get('volume', 'не указано')}"
    )
    """
    # Используем фото со стильной рамкой
    framed_photo = await resize_photo(perfume["photo"], 
                                     max_size=(800, 800), 
                                     border_radius=20, 
                                     shadow_offset=8)
    """
    framed_photo = get_photo_input(perfume)
    await callback.message.answer_photo(
        photo=framed_photo,
        caption=caption,
        reply_markup=category_card_keyboard(
    0,
    len(items),
    "gender",
    perfume,
    callback.from_user.id
),

        parse_mode="HTML"
    )
    
    await callback.answer()

@dp.callback_query(F.data.regexp(r"^(gender|scent)_(prev|next)_\d+$"))
async def category_navigation_handler(callback: CallbackQuery, state: FSMContext):
    prefix, direction, current = callback.data.split("_")
    current = int(current)
    telegram_id = callback.from_user.id
    data = await state.get_data()
    items = data.get("cat_items", [])
    
    if not items:
        await callback.answer("Данные не найдены")
        return

    if direction == "next" and current < len(items) - 1:
        index = current + 1
    elif direction == "prev" and current > 0:
        index = current - 1
    else:
        await callback.answer()
        return

    await state.update_data(
    back_view="category",
    back_index=index,
    back_items=items,
    back_prefix=prefix
)
    perfume = items[index]
    
    # Формируем список категорий для отображения
    categories = []
    category2 = perfume.get("category2", [])
    
    if isinstance(category2, str):
        categories = [category2]
    elif isinstance(category2, list):
        categories = category2
    elif not category2:
        categories = [perfume.get("category", "не указано")]
    
    # Формируем текст категорий
    if isinstance(categories, list) and len(categories) > 0:
        categories_text = ", ".join(categories)
    else:
        categories_text = str(categories)
    
    caption = (
        f"<b>{perfume['name']}</b>\n"
        f"Пол: {categories_text}\n"
        f"Объём: {perfume.get('volume', 'не указано')}"
    )

    # Используем фото со стильной рамкой
    """
    framed_photo = await resize_photo(
        perfume["photo"], 
        max_size=(800, 800), 
        border_radius=20, 
        shadow_offset=8
    )
    """
    framed_photo = get_photo_input(perfume)
    await callback.message.edit_media(
        media=InputMediaPhoto(
            media=framed_photo,
            caption=caption,
            parse_mode="HTML"
        ),
        reply_markup=category_card_keyboard(index,len(items),prefix,perfume,telegram_id)
    )

    await callback.answer()

@dp.message(F.text == "📂 Категории")
async def show_categories(message: Message, state: FSMContext):
    await message.answer(
        "📂 В данном разделе Вы сможете выбрать нужную категорию ароматов:",
        reply_markup=categories_keyboard()
    )

def catalog_card_keyboard(index: int, telegram_id: int):
    perfume = perfumes[index]
    fav_text, fav_cb = favorite_button(telegram_id,perfume["id"],source="catalog",index=index)

    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️", callback_data=f"nav_prev_{index}")
    kb.button(text=f"{index+1}/{len(perfumes)}", callback_data="noop")
    kb.button(text="➡️", callback_data=f"nav_next_{index}")

    kb.button(text="ℹ️ Подробнее", callback_data=f"perf_{perfume['id']}")
    kb.button(text=fav_text, callback_data=fav_cb)
    
    kb.adjust(3, 1, 1)

    return kb.as_markup()
def get_detail_photo(perfume):
    photo2 = perfume.get("photo2")
    if not photo2:
        return FSInputFile(NO_IMAGE_PATH)

    path = BASE_DIR / photo2
    if path.exists():
        return FSInputFile(path)

    print(f"[WARN] detail photo not found: {path}")
    return FSInputFile(NO_IMAGE_PATH)
@dp.callback_query(F.data.startswith("perf_"))
async def show_perfume(callback: CallbackQuery, state: FSMContext):
    perfume_id = int(callback.data.replace("perf_", ""))
    await track(callback.from_user.id, "view_perfume", perfume_id)
    perfume_index = next(i for i, p in enumerate(perfumes) if p["id"] == perfume_id)
    perfume = perfumes[perfume_index]
    
    # Сохраняем ID оригинальной карточки товара
    original_card_id = callback.message.message_id
    
    # Сохраняем данные для возврата
    await state.update_data(
        origin_view="catalog",  # Добавляем источник
        origin_index=perfume_index,  # Добавляем индекс
        original_card_id=original_card_id  # ID карточки товара для возврата
    )
    
    # 📸 фото
    

    photo_msg = await callback.message.answer_photo(
        photo=get_detail_photo_input(perfume)
    )
    await state.update_data(order_photo_id=photo_msg.message_id)

    # 📝 описание
    description_msg = await callback.message.answer(
        f"<b>Описание:</b>\n{perfume.get('description','')}",
        reply_markup=order_keyboard("catalog", perfume_index, perfume_id),
        parse_mode="HTML"
    )
    
    # Сохраняем ID сообщения с описанием для последующего удаления
    await state.update_data(description_msg_id=description_msg.message_id)

    await callback.answer()


@dp.callback_query(F.data.regexp(r"^search_(prev|next)_\d+$"))
async def search_navigation(callback: CallbackQuery, state: FSMContext):
    _, direction, current = callback.data.split("_")
    current = int(current)

    data = await state.get_data()
    results = data["search_results"]
    index = data["search_index"]

    if direction == "next" and current < len(results) - 1:
        index = current + 1
    elif direction == "prev" and current > 0:
        index = current - 1
    else:
        await callback.answer()
        return

    await state.update_data(
    search_index=index,
    back_view="search",
    back_index=index,
    back_results=results
)

    perfume = results[index]
    """
    # Используем фото со стильной рамкой
    framed_photo = await resize_photo(perfume["photo"], 
                                     max_size=(800, 800), 
                                     border_radius=20, 
                                     shadow_offset=8)
    """
    framed_photo = get_photo_input(perfume)
    await callback.message.edit_media(
        media=InputMediaPhoto(
            media=framed_photo,
            caption=(
                f"<b>{perfume['name']}</b>\n"
                f"Пол: {perfume.get('category', 'не указано')}\n"
                f"Объём: {perfume.get('volume', 'не указано')}\n"
            ),
            parse_mode="HTML"
        ),
            reply_markup=search_card_keyboard(
        index,
        len(results),
        callback.from_user.id,
        perfume
    )
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("search_open_"))
async def search_open(callback: CallbackQuery, state: FSMContext):
    index = int(callback.data.split("_")[-1])
    
    data = await state.get_data()
    results = data["search_results"]
    perfume = results[index]

    # Сохраняем ID оригинальной карточки товара
    original_card_id = callback.message.message_id
    
    # Сохраняем данные для возврата
    await state.update_data(
        origin_view="search",  # Добавляем источник
        origin_index=index,  # Добавляем индекс
        original_card_id=original_card_id  # ID карточки товара для возврата
    )
    #photo_path = BASE_DIR / perfume["photo2"]
    
    photo_msg = await callback.message.answer_photo(
        photo=get_detail_photo_input(perfume)
    )

    await state.update_data(order_photo_id=photo_msg.message_id)

    await callback.message.answer(
        f"<b>Описание:</b>\n{perfume.get('description','')}",
        reply_markup=order_keyboard("search", index,perfume["id"]),  # source остается "search"
        parse_mode="HTML"
    )

    await callback.answer()
def get_detail_photo_input(perfume: dict):
    raw = perfume.get("photo2_url") or perfume.get("photo2")
    url = normalize_photo_url(raw)

    if url:
        return URLInputFile(url)

    # fallback: если фото2 хранится локально (опционально)
    photo2 = perfume.get("photo2")
    if isinstance(photo2, str) and photo2:
        filename = photo2.split("/")[-1]
        path = PHOTOS_DIR / filename
        if path.exists():
            return FSInputFile(path)

    return FSInputFile(NO_IMAGE_PATH)
# Обработчики поиска по разным типам
@dp.message(SearchState.waiting_query)
async def search_by_name_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
    await track(message.from_user.id, "open_favorites", username=username)
    # ✅ Если снова нажали кнопку "🔍 Поиск" во время поиска — НЕ ищем, а просто подсказываем
    if text == "🔍 Поиск":
        await message.answer("🔍 Вы уже находитесь в поиске.\nВведите название аромата:")
        return

    query = text.lower()

    # защита от пустого ввода
    if not query:
        await message.answer("Введите название аромата для поиска:")
        return

    results = search_perfumes(query)

    # ❌ Ничего не найдено — остаёмся в поиске и просим ввести ещё раз
    if not results:
        await message.answer("😔 По Вашему запросу ничего не найдено. Попробуйте ещё раз:")
        return

    # ✅ Есть результаты
    perfume = results[0]

    await state.update_data(
        search_results=results,
        search_index=0,
        search_type="mixed",
        search_query=query,
        back_view="search",
        back_index=0
    )
    """
    framed_photo = await resize_photo(perfume["photo"])
    """
    framed_photo = get_photo_input(perfume)
    await message.answer_photo(
        photo=framed_photo,
        caption=(
            f"<b>{perfume['name']}</b>\n"
            f"Пол: {perfume.get('category', 'не указано')}\n"
            f"Объём: {perfume.get('volume', 'не указано')}"
        ),
        reply_markup=search_card_keyboard(0, len(results), message.from_user.id, perfume),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "back")
async def back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(
        "В данном разделе Вы сможете выбрать нужную категорию ароматов:",
        reply_markup=categories_keyboard()
    )
@dp.message(F.text == "🔍 Поиск", StateFilter("*"))
async def search_reply(message: Message, state: FSMContext):
    current_state = await state.get_state()
    
    if current_state == SearchState.waiting_query:
        await message.answer("🔍 Вы уже находитесь в поиске.\nВведите название аромата:")
        return
    
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
    await track(message.from_user.id, "search_click", username=username)
    await state.set_state(SearchState.waiting_query)
    await message.answer(
        "Поиск по названию Вашего любимого аромата известного бренда либо по названию аромата нашего бренда. Введите название:",
        parse_mode="HTML"
    )


@dp.callback_query(F.data.regexp(r"^(gender|scent)_(prev|next)_\d+$"))
async def category_navigation_handler(callback: CallbackQuery, state: FSMContext):
    prefix, direction, current = callback.data.split("_")
    current = int(current)

    data = await state.get_data()
    items = data.get("cat_items", [])
    
    if not items:
        await callback.answer("Данные не найдены")
        return

    if direction == "next" and current < len(items) - 1:
        index = current + 1
    elif direction == "prev" and current > 0:
        index = current - 1
    else:
        await callback.answer()
        return

    await state.update_data(
    back_view="category",
    back_index=index,
    back_items=items,
    back_prefix=prefix
)
    perfume = items[index]
    
    # Добавляем информацию о поле и объеме
    caption = (
        f"<b>{perfume['name']}</b>\n"
        f"Пол: {perfume.get('category', 'не указано')}\n"
        f"Объём: {perfume.get('volume', 'не указано')}"
    )

    await callback.message.edit_media(
        media=InputMediaPhoto(
            media=FSInputFile(perfume["photo"]),
            caption=caption,
            parse_mode="HTML"
        ),
        reply_markup=category_card_keyboard(index, len(items), prefix, perfume)
    )

    await callback.answer()

@dp.callback_query(F.data.regexp(r"^nav_(prev|next)_\d+$"))
async def catalog_navigation(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    parts = callback.data.split("_")
    
    if len(parts) != 3:
        await callback.answer("Неверный формат данных")
        return
    
    direction = parts[1]
    index = int(parts[2])

    # Удаляем старое фото из описания если есть
    data = await state.get_data()
    old_photo_id = data.get("order_photo_id")
    if old_photo_id:
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=old_photo_id
            )
        except:
            pass
        await state.update_data(order_photo_id=None)
    
    # Также удаляем сообщение с описанием, если оно открыто
    # Вы можете сохранить message_id описания в состоянии при открытии
    description_msg_id = data.get("description_msg_id")
    if description_msg_id:
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=description_msg_id
            )
        except:
            pass
        await state.update_data(description_msg_id=None)

    if direction == "next" and index < len(perfumes) - 1:
        index += 1
    elif direction == "prev" and index > 0:
        index -= 1
    else:
        await callback.answer()
        return

    perfume = perfumes[index]
    """"
    # Используем фото со стильной рамкой
    framed_photo = await resize_photo(perfume["photo"],  
                                     border_radius=20, 
                                     shadow_offset=4)
    """
    framed_photo = get_photo_input(perfume)
    if not framed_photo:
        await callback.answer("У товара нет photo_url", show_alert=True)
        return
    media = InputMediaPhoto(
    media=framed_photo,
    caption=(
        f"<b>{perfume['name']}</b>\n"
        f"Пол: {perfume['category']}\n"
        f"Объём: {perfume['volume']}\n"
    ),
    parse_mode="HTML"
)

    await callback.message.edit_media(
        media=media,
        reply_markup=catalog_card_keyboard(index=index,
        telegram_id=callback.from_user.id)
    )

    await callback.answer()

@dp.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()

def category_card_keyboard(index: int, total: int, prefix: str, perfume, telegram_id: int):
    kb = InlineKeyboardBuilder()

    # Навигация
    kb.button(text="⬅️", callback_data=f"{prefix}_prev_{index}")
    kb.button(text=f"{index+1}/{total}", callback_data="noop")
    kb.button(text="➡️", callback_data=f"{prefix}_next_{index}")

    # Подробнее
    kb.button(
        text="ℹ️ Подробнее",
        callback_data=f"cat_open_{prefix}_{index}"
    )
    fav_text, fav_cb = favorite_button(telegram_id,perfume["id"],source="category",index=index)

    kb.button(text=fav_text, callback_data=fav_cb)
    kb.adjust(3, 1, 1)
    return kb.as_markup()

def normalize_scent(value):
    # приводит к списку строк
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).casefold().strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        # если это JSON-список строкой
        if s.startswith("["):
            try:
                arr = json.loads(s)
                if isinstance(arr, list):
                    return [str(x).casefold().strip() for x in arr if str(x).strip()]
            except Exception:
                pass
        # иначе одиночное значение
        return [s.casefold()]
    return []
@dp.callback_query(F.data.startswith("cat_scent_"))
async def show_scent_category_handler(callback: CallbackQuery, state: FSMContext):
    

    scent_map = {
        "floral": "цветочные",
        "citrus": "цитрусовые",
        "niche": "нишевые",
        "woody": "древесные",
        "oriental": "восточные",
        "fruity": "фруктовые",
    }

    key = callback.data.removeprefix("cat_scent_").strip().lower()

    if key not in scent_map:
        await callback.answer(f"❌ Неизвестная категория: {key}")
        return

    category = scent_map[key]
    category_lower = category.casefold()

    items = []
    for p in perfumes:
        raw_scent = p.get("scent_category")
        if not raw_scent:
            raw_scent = (p.get("details_json") or {}).get("scent_category")
        if isinstance(raw_scent, str):
            s = raw_scent.strip()
            if s.startswith("["):
                try:
                    arr = json.loads(s)
                    if isinstance(arr, list):
                        scent_list = [str(x).casefold().strip() for x in arr]
                except Exception:
                    scent_list = [s.casefold()]
            else:
                scent_list = [s.casefold()]
        elif isinstance(raw_scent, list):
            scent_list = [str(x).casefold().strip() for x in raw_scent]
        if any(category_lower in s for s in scent_list):
            items.append(p)

    if not items:
        await callback.message.answer("😔 В этой категории пока нет товаров")
        print("DEBUG found:", len(items))
        print("DEBUG example product:", perfumes[0])
        await callback.answer()
        return

    await state.update_data(
    cat_items=items,
    cat_index=0,
    cat_type="scent"
)

    perfume = items[0]  # ✅ ВАЖНО: сначала объявили

    photo = get_photo_input(perfume)  # ✅ теперь можно

    caption = (
        f"<b>{perfume['name']}</b>\n"
        f"Пол: {perfume.get('category', 'не указано')}\n"
        f"Объём: {perfume.get('volume', 'не указано')}"
    )

    await callback.message.answer_photo(
    photo=photo,
    caption=caption,
    reply_markup=category_card_keyboard(
        0,
        len(items),
        "scent",
        perfume,
        callback.from_user.id
    ),
    parse_mode="HTML",
)

    await callback.answer()


@dp.callback_query(F.data.startswith("cat_open_"))
async def category_open(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")

    if len(parts) < 4:
        await callback.answer("Ошибка навигации", show_alert=True)
        return

    category_type = parts[2]
    index = int(parts[3])

    data = await state.get_data()
    items = data.get("cat_items", [])

    if index < 0 or index >= len(items):
        await callback.answer("Товар не найден", show_alert=True)
        return

    perfume = items[index]

    # Сохраняем ID оригинальной карточки товара
    original_card_id = callback.message.message_id
    
    # Сохраняем данные для возврата
    await state.update_data(
        back_view="category",
        back_items=items,
        back_index=index,
        back_prefix=category_type,
        origin_view="category",  # Добавляем источник
        origin_index=index,  # Добавляем индекс
        original_card_id=original_card_id  # ID карточки товара для возврата
    )
    
    photo_msg = await callback.message.answer_photo(
        photo=get_detail_photo_input(perfume)
    )
    
   
    await state.update_data(order_photo_id=photo_msg.message_id)

    await callback.message.answer(
        f"<b>Описание:</b>\n{perfume.get('description','')}",
        reply_markup=order_keyboard("category", index,perfume["id"]),  # Изменяем source на "category"
        parse_mode="HTML"
    )

    await callback.answer()
async def periodic_reload():
    global perfumes
    while True:
        try:
            perfumes = await fetch_perfumes()
        except Exception as e:
            print("Reload error:", e)
        await asyncio.sleep(60)

async def main():
    global perfumes
    perfumes = await fetch_perfumes()
    await bot.set_my_commands([])
    asyncio.create_task(periodic_reload())
    await bot.set_chat_menu_button(
        menu_button=MenuButtonDefault()
    )
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())