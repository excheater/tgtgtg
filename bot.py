import os
import asyncio
import glob
import logging
import subprocess
import yt_dlp
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties

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

def cleanup(path: str):
    if path and os.path.exists(path):
        try: os.remove(path)
        except: pass

def get_ydl_opts():
    return {
        "quiet": True, "no_warnings": True, "socket_timeout": 30, "retries": 10,
        "concurrent_fragment_downloads": 20, "buffersize": 1024 * 512,
        "http_headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"},
    }

def split_video_by_time(input_file: str, segment_seconds: int) -> list[str]:
    if not os.path.exists(input_file): return []
    base_name = os.path.splitext(input_file)[0]
    output_pattern = f"{base_name}_part%03d.mp4"
    # -c copy сохраняет оригинальное соотношение сторон и не тратит CPU
    cmd = ['ffmpeg', '-i', input_file, '-c', 'copy', '-map', '0', '-segment_time', str(segment_seconds), '-f', 'segment', '-reset_timestamps', '1', output_pattern]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, check=True)
        return sorted(glob.glob(f"{base_name}_part*.mp4"))
    except: return [input_file]

def get_settings_keyboard(uid: int):
    data = pending.get(uid)
    q = data.get("qual", 720)
    d = data.get("dur", 30)

    kb = InlineKeyboardBuilder()
    # Ряд КАЧЕСТВО
    kb.button(text=f"{'✅ ' if q == 720 else ''}720p", callback_data=f"set_{uid}_q_720")
    kb.button(text=f"{'✅ ' if q == 480 else ''}480p", callback_data=f"set_{uid}_q_480")
    # Ряд ВРЕМЯ
    kb.button(text=f"{'✅ ' if d == 30 else ''}30 сек", callback_data=f"set_{uid}_d_30")
    kb.button(text=f"{'✅ ' if d == 15 else ''}15 сек", callback_data=f"set_{uid}_d_15")
    # Кнопка СКАЧАТЬ
    kb.button(text="🚀 СКАЧАТЬ", callback_data=f"start_dl_{uid}")
    
    kb.adjust(2, 2, 1)
    return kb.as_markup()

dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer("👋 Пришли ссылку на видео, выбери качество и время нарезки!")

@dp.message(F.text.startswith("http"))
async def handle_url(message: Message):
    url = message.text.strip()
    msg = await message.answer("🔍 Анализирую...")
    try:
        opts = {**get_ydl_opts(), "skip_download": True}
        loop = asyncio.get_event_loop()
        # Извлекаем инфо без скачивания
        info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(opts).extract_info(url, download=False))
        
        uid = message.from_user.id
        pending[uid] = {
            "url": url, 
            "title": info.get("title", "video"),
            "qual": 720, # Дефолт
            "dur": 30    # Дефолт
        }

        await msg.edit_text(
            f"🎬 <b>{info.get('title')[:100]}</b>\n\nНастройте параметры:",
            reply_markup=get_settings_keyboard(uid)
        )
    except Exception:
        await msg.edit_text("❌ Не удалось проанализировать ссылку.")

@dp.callback_query(F.data.startswith("set_"))
async def handle_settings(callback: CallbackQuery):
    _, uid, mode, val = callback.data.split("_")
    uid, val = int(uid), int(val)

    if callback.from_user.id != uid or uid not in pending:
        return await callback.answer("Сессия устарела.")

    if mode == "q": pending[uid]["qual"] = val
    else: pending[uid]["dur"] = val

    # Обновляем кнопки с галочками
    await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(uid))
    await callback.answer()

@dp.callback_query(F.data.startswith("start_dl_"))
async def handle_dl(callback: CallbackQuery, bot: Bot):
    uid = int(callback.data.split("_")[-1])

    if callback.from_user.id != uid or uid not in pending:
        return await callback.answer("Ошибка данных.")

    if download_lock.locked():
        return await callback.answer("⏳ Бот занят. Пожалуйста, подождите...", show_alert=True)

    async with download_lock:
        data = pending.pop(uid)
        qual, dur = data["qual"], data["dur"]
        
        status_msg = await callback.message.edit_text(f"🚀 Загрузка: {qual}p | Нарезка: {dur}s")
        raw_path = f"{DOWNLOAD_DIR}/{uid}_{qual}.mp4"
        
        try:
            # Запрашиваем формат с приоритетом 16:9 (aspect_ratio > 1)
            ydl_opts = {
                **get_ydl_opts(),
                "outtmpl": raw_path,
                "format": f"bestvideo[height<={qual}][aspect_ratio>1][ext=mp4]+bestaudio[ext=m4a]/best[height<={qual}]/best",
                "merge_output_format": "mp4"
            }
            
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: yt_dlp.YoutubeDL(ydl_opts).download([data['url']])
            )
            
            await status_msg.edit_text(f"✂️ Нарезка по {dur} секунд...")
            parts = await asyncio.get_event_loop().run_in_executor(
                None, lambda: split_video_by_time(raw_path, dur)
            )
            
            for i, part in enumerate(parts):
                size_mb = os.path.getsize(part) / (1024 * 1024)
                caption = f"🎬 {data['title'][:50]}\n📦 Часть {i+1}/{len(parts)} | {qual}p | {dur}s"
                
                # Явно задаем width и height для Telegram, чтобы избежать 1:1
                w, h = (1280, 720) if qual == 720 else (854, 480)
                
                await bot.send_video(
                    chat_id=callback.message.chat.id,
                    video=FSInputFile(part),
                    caption=caption,
                    supports_streaming=True,
                    width=w, height=h,
                    request_timeout=600
                )
                cleanup(part)
                await asyncio.sleep(1.5) # Защита от лимитов Railway

            await status_msg.delete()
            
        except Exception as e:
            logger.error(f"Error: {e}")
            await callback.message.answer("❌ Произошла ошибка.")
        finally:
            cleanup(raw_path)

async def main():
    for f in glob.glob(f"{DOWNLOAD_DIR}/*"): cleanup(f)
    session = AiohttpSession(timeout=3600)
    bot = Bot(token=BOT_TOKEN, session=session, base_url=f"{LOCAL_API}/", default=DefaultBotProperties(parse_mode="HTML"))
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, polling_timeout=30)

if __name__ == "__main__":
    asyncio.run(main())
