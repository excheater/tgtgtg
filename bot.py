import os
import asyncio
import glob
import logging
import subprocess
import yt_dlp
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery, FSInputFile, 
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.client.telegram import TelegramAPIServer # Обязательно для локального API
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================
BOT_TOKEN = os.environ.get("8096946406:AAFdBx7XWYvVg7qUUwr_JC-pVbplr2JN4-E", "8096946406:AAFdBx7XWYvVg7qUUwr_JC-pVbplr2JN4-E")
LOCAL_API = os.environ.get("LOCAL_API_URL", "http://telegram-bot-api:8081")
# =============================================

Вот полный, исправленный и оптимизированный код для Railway. Я учел последнюю ошибку с base_url и переписал инициализацию через TelegramAPIServer, как того требует aiogram 3.x.

Что внутри:
Выбор качества и времени: Интерактивное меню (720/480p и 30/15 сек).

Кнопка СТОП: Большая кнопка под вводом текста для мгновенной отмены.

Очередь: Обработка строго по одному видео, чтобы не «повесить» сервер.

Защита 16:9: Видео не будет квадратным.

Cookies: Поддержка cookies.txt для обхода блокировок YouTube.

Python

import os
import asyncio
import glob
import logging
import subprocess
import yt_dlp
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery, FSInputFile, 
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.client.telegram import TelegramAPIServer  # Для работы с локальным API

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8715702797:AAGQFyhgNGlzbFsH1SgDIqJ2tF6rbj9CwXE")
LOCAL_API = os.environ.get("LOCAL_API_URL", "http://telegram-bot-api:8081")
# =============================================

DOWNLOAD_DIR = "./downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

download_lock = asyncio.Lock()
pending = {}
active_tasks = {} # Флаги отмены {user_id: bool}

def cleanup(path: str):
    if path and os.path.exists(path):
        try: os.remove(path)
        except: pass

def get_ydl_opts():
    return {
        "quiet": True, 
        "no_warnings": True, 
        "socket_timeout": 30, 
        "retries": 10,
        "cookiefile": "cookies.txt", 
        "concurrent_fragment_downloads": 20, 
        "buffersize": 1024 * 512,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        },
    }

def split_video_by_time(input_file: str, segment_seconds: int) -> list[str]:
    if not os.path.exists(input_file): return []
    base_name = os.path.splitext(input_file)[0]
    output_pattern = f"{base_name}_part%03d.mp4"
    
    cmd = [
        'ffmpeg', '-i', input_file, 
        '-c', 'copy', '-map', '0', 
        '-segment_time', str(segment_seconds), 
        '-f', 'segment', '-reset_timestamps', '1', 
        output_pattern
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, check=True)
        return sorted(glob.glob(f"{base_name}_part*.mp4"))
    except:
        return [input_file]

def get_settings_keyboard(uid: int):
    data = pending.get(uid)
    q = data.get("qual", 720)
    d = data.get("dur", 30)
    
    kb = InlineKeyboardBuilder()
    kb.button(text=f"{'✅ ' if q == 720 else ''}720p", callback_data=f"set_{uid}_q_720")
    kb.button(text=f"{'✅ ' if q == 480 else ''}480p", callback_data=f"set_{uid}_q_480")
    kb.button(text=f"{'✅ ' if d == 30 else ''}30 сек", callback_data=f"set_{uid}_d_30")
    kb.button(text=f"{'✅ ' if d == 15 else ''}15 сек", callback_data=f"set_{uid}_d_15")
    kb.button(text="🚀 СКАЧАТЬ", callback_data=f"start_dl_{uid}")
    kb.adjust(2, 2, 1)
    return kb.as_markup()

stop_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🛑 ОСТАНОВИТЬ")]],
    resize_keyboard=True
)

dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer("🚀 Пришли ссылку на видео!", reply_markup=ReplyKeyboardRemove())

@dp.message(F.text == "🛑 ОСТАНОВИТЬ")
async def handle_stop_text(message: Message):
    uid = message.from_user.id
    if uid in active_tasks:
        active_tasks[uid] = False
        await message.answer("🛑 Сигнал остановки получен...", reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer("Нет активных процессов.", reply_markup=ReplyKeyboardRemove())

@dp.message(F.text.startswith("http"))
async def handle_url(message: Message):
    url = message.text.strip()
    msg = await message.answer("🔍 Анализирую...")
    try:
        opts = {**get_ydl_opts(), "skip_download": True}
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(opts).extract_info(url, download=False))
        
        uid = message.from_user.id
        pending[uid] = {"url": url, "title": info.get("title", "video"), "qual": 720, "dur": 30}
        await msg.edit_text(f"🎬 <b>{info.get('title')[:100]}</b>\nНастройки:", reply_markup=get_settings_keyboard(uid))
    except Exception as e:
        logger.error(f"Error: {e}")
        await msg.edit_text("❌ Ошибка. Проверьте cookies.txt или ссылку.")

@dp.callback_query(F.data.startswith("set_"))
async def handle_settings(callback: CallbackQuery):
    _, uid, mode, val = callback.data.split("_")
    uid, val = int(uid), int(val)
    if uid not in pending: return
    if mode == "q": pending[uid]["qual"] = val
    else: pending[uid]["dur"] = val
    await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(uid))
    await callback.answer()

@dp.callback_query(F.data.startswith("start_dl_"))
async def handle_dl(callback: CallbackQuery, bot: Bot):
    uid = int(callback.data.split("_")[-1])
    if uid not in pending: return
    
    if download_lock.locked():
        return await callback.answer("⏳ Очередь занята, подождите...", show_alert=True)

    async with download_lock:
        if uid not in pending: return
        data = pending.pop(uid)
        qual, dur = data["qual"], data["dur"]
        active_tasks[uid] = True
        
        status_msg = await bot.send_message(
            chat_id=callback.message.chat.id,
            text=f"⏳ Начинаю: {qual}p | {dur}с.",
            reply_markup=stop_keyboard
        )
        await callback.message.delete()
        
        raw_path = f"{DOWNLOAD_DIR}/{uid}_{qual}.mp4"
        try:
            ydl_opts = {
                **get_ydl_opts(), 
                "outtmpl": raw_path, 
                "format": f"bestvideo[height<={qual}][aspect_ratio>1][ext=mp4]+bestaudio[ext=m4a]/best[height<={qual}]/best", 
                "merge_output_format": "mp4"
            }
            await asyncio.get_event_loop().run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).download([data['url']]))
            
            if not active_tasks.get(uid): raise InterruptedError()

            parts = await asyncio.get_event_loop().run_in_executor(None, lambda: split_video_by_time(raw_path, dur))
            
            for i, part in enumerate(parts):
                if not active_tasks.get(uid): raise InterruptedError()
                
                w, h = (1280, 720) if qual == 720 else (854, 480)
                await bot.send_video(
                    chat_id=callback.message.chat.id, video=FSInputFile(part),
                    caption=f"📦 Часть {i+1}/{len(parts)}",
                    width=w, height=h, supports_streaming=True
                )
                cleanup(part)
                await asyncio.sleep(1.5)

        except InterruptedError:
            for f in glob.glob(f"{DOWNLOAD_DIR}/{uid}_*"): cleanup(f)
        except Exception as e:
            logger.error(f"Error: {e}")
            await bot.send_message(uid, "❌ Ошибка обработки.")
        finally:
            active_tasks.pop(uid, None)
            cleanup(raw_path)
            await bot.send_message(uid, "✅ Готово.", reply_markup=ReplyKeyboardRemove())

async def main():
    for f in glob.glob(f"{DOWNLOAD_DIR}/*"): cleanup(f)
    
    # ПРАВИЛЬНОЕ ПОДКЛЮЧЕНИЕ К ЛОКАЛЬНОМУ API ДЛЯ AIOGRAM 3.X
    local_server = TelegramAPIServer.from_base(LOCAL_API)
    session = AiohttpSession(timeout=3600, api_server=local_server)
    
    bot = Bot(
        token=BOT_TOKEN, 
        session=session, 
        default=DefaultBotProperties(parse_mode="HTML")
    )
    
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("🤖 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
