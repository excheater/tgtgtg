
import os, asyncio, glob, logging, subprocess, yt_dlp
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, FSInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8096946406:AAFdBx7XWYvVg7qUUwr_JC-pVbplr2JN4-E"
LOCAL_API = os.environ.get("LOCAL_API_URL", "http://telegram-bot-api:8081")

DOWNLOAD_DIR = "./downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

user_modes = {}
pending_data = {}

def cleanup_file(path: str):
    try:
        if path and os.path.exists(path): os.remove(path)
    except: pass

def split_video(input_file: str, segment_seconds: int = 30) -> list[str]:
    base_name = os.path.splitext(input_file)[0]
    output_pattern = f"{base_name}_part%03d.mp4"
    cmd = ['ffmpeg', '-i', input_file, '-c', 'copy', '-map', '0', '-segment_time', str(segment_seconds), '-f', 'segment', '-reset_timestamps', '1', output_pattern]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return sorted(glob.glob(f"{base_name}_part*.mp4"))

async def process_and_send(event, file_path, title, qual, bot):
    try:
        parts = split_video(file_path, 30)
        for i, part in enumerate(parts):
            await bot.send_video(
                chat_id=event.from_user.id,
                video=FSInputFile(part),
                caption=f"📦 Часть {i+1}/{len(parts)} | {title[:30]}",
                width=1280 if qual >= 720 else 854,
                height=qual,
                supports_streaming=True
            )
            await asyncio.sleep(1.5)
            cleanup_file(part)
        await bot.send_message(event.from_user.id, "✅ Обработка завершена!")
    finally:
        cleanup_file(file_path)

dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(message: Message):
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔗 Ссылка"), KeyboardButton(text="📂 Файл")]], resize_keyboard=True)
    await message.answer("Выбери режим:", reply_markup=kb)

@dp.message(F.text == "🔗 Ссылка")
async def m_l(m: Message):
    user_modes[m.from_user.id] = "link"
    await m.answer("Жду ссылку...", reply_markup=ReplyKeyboardRemove())

@dp.message(F.text == "📂 Файл")
async def m_f(m: Message):
    user_modes[m.from_user.id] = "file"
    await m.answer("Кидай видео (хоть 2ГБ)...", reply_markup=ReplyKeyboardRemove())

@dp.message(F.video | F.document)
async def handle_user_video(message: Message, bot: Bot):
    if user_modes.get(message.from_user.id) != "file": return
    video = message.video or message.document
    msg = await message.answer("⚡ Локальный сервер принял файл. Копирую...")
    
    try:
        local_path = os.path.join(DOWNLOAD_DIR, f"fix_{video.file_id}.mp4")
        await bot.download(video.file_id, destination=local_path)
        await msg.edit_text("✂️ Нарезаю...")
        await process_and_send(message, local_path, "Свой файл", 720, bot)
        await msg.delete()
    except Exception as e:
        logger.error(f"Ошибка загрузки файла: {e}")
        await msg.edit_text(f"❌ Ошибка:
{str(e)[:300]}")

async def main():
    bot = Bot(token=BOT_TOKEN, session=AiohttpSession(), base_url=f"{LOCAL_API}/", default=DefaultBotProperties(parse_mode="HTML"))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
