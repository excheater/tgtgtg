import os, asyncio, glob, logging, subprocess, aiohttp, aiofiles, shutil
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import CommandStart
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("8096946406:AAFdBx7XWYvVg7qUUwr_JC-pVbplr2JN4-E", "8096946406:AAFdBx7XWYvVg7qUUwr_JC-pVbplr2JN4-E")
LOCAL_API  = os.environ.get("http://telegram-bot-api-massons.railway.internal:8081", "http://telegram-bot-api-massons.railway.internal:8081")

DOWNLOAD_DIR = "./downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

user_cut = {}


def cleanup_file(path: str):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def cleanup_all():
    for f in glob.glob(f"{DOWNLOAD_DIR}/*"):
        try:
            os.remove(f)
        except Exception:
            pass


def split_video(input_file: str, segment_seconds: int) -> list:
    base = os.path.splitext(input_file)[0]
    output_pattern = f"{base}_part%03d.mp4"
    result = subprocess.run([
        "ffmpeg", "-i", input_file,
        "-c", "copy", "-map", "0",
        "-segment_time", str(segment_seconds),
        "-f", "segment",
        "-reset_timestamps", "1",
        output_pattern
    ], capture_output=True, text=True)
    logger.info(f"ffmpeg: {result.returncode}, stderr: {result.stderr[-200:]}")
    return sorted(glob.glob(f"{base}_part*.mp4"))


async def download_file(file_id: str, dest: str):
    """
    Скачивает файл через локальный Bot API.
    """
    logger.info(f"LOCAL_API = {LOCAL_API}")
    # Шаг 1: getFile через локальный API
    url = f"{LOCAL_API.rstrip('/')}/bot{BOT_TOKEN}/getFile"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params={"file_id": file_id}) as resp:
            data = await resp.json()
            if not data.get("ok"):
                raise Exception(f"getFile error: {data}")
            file_path = data["result"]["file_path"]
            logger.info(f"file_path: {file_path}")

    # Шаг 2: если это абсолютный путь и файл существует — копируем
    if os.path.isabs(file_path) and os.path.exists(file_path):
        logger.info(f"Копируем напрямую: {file_path} -> {dest}")
        await asyncio.get_event_loop().run_in_executor(None, shutil.copy2, file_path, dest)
        return

    # Локальный Bot API — файл доступен по пути который вернул getFile
    # file_path уже содержит полный путь внутри контейнера telegram-bot-api
    # Нужно скачать через HTTP endpoint локального сервера
    base = LOCAL_API.rstrip('/')
    
    # Сначала проверяем что отвечает сервер
    async with aiohttp.ClientSession() as session:
        # Пингуем сервер
        try:
            async with session.get(f"{base}/") as r:
                body = await r.text()
                logger.info(f"Ping {base}/: HTTP {r.status}, body={body[:200]}")
        except Exception as e:
            logger.warning(f"Ping failed: {e}")

        # Локальный telegram-bot-api отдаёт файлы через endpoint:
        # GET /file/botTOKEN/path  — НО только если запущен с флагом --local
        # При --local файлы хранятся в --dir и отдаются напрямую
        # Локальный Bot API при флаге --local хранит файлы в /var/lib/telegram-bot-api/
        # и отдаёт их через: /var/lib/telegram-bot-api/BOT_TOKEN/videos/file_0.MP4
        # file_path от локального API выглядит как: videos/file_0.MP4
        # Полный путь на сервере: /var/lib/telegram-bot-api/BOT_TOKEN/videos/file_0.MP4
        # HTTP endpoint: GET /botTOKEN/FILEPATH (без /file/)
        candidates = [
            f"{base}/bot{BOT_TOKEN}/{file_path}",
            f"{base}/file/bot{BOT_TOKEN}/{file_path}",
            f"{base}/{BOT_TOKEN}/{file_path}",
            f"{base}/{file_path}",
        ]
        last_status = None
        last_body = None
        for url in candidates:
            logger.info(f"GET {url}")
            try:
                async with session.get(url) as resp:
                    last_status = resp.status
                    if resp.status == 200:
                        logger.info(f"OK: {url}")
                        async with aiofiles.open(dest, "wb") as f:
                            async for chunk in resp.content.iter_chunked(1024 * 1024):
                                await f.write(chunk)
                        return
                    else:
                        last_body = await resp.text()
                        logger.warning(f"HTTP {resp.status}: {last_body[:100]}")
            except Exception as e:
                logger.warning(f"Error {url}: {e}")
        raise Exception(f"Не удалось скачать. Последний статус: {last_status}, тело: {last_body}")


async def send_parts(chat_id: int, parts: list, title: str, bot: Bot):
    total = len(parts)
    for i, part in enumerate(parts, 1):
        size_mb = os.path.getsize(part) / (1024 * 1024)
        try:
            await bot.send_video(
                chat_id=chat_id,
                video=FSInputFile(part),
                caption=f"📦 {i}/{total} | {title[:50]} | {size_mb:.1f} MB",
                supports_streaming=True,
                request_timeout=300,
            )
        except Exception as e:
            logger.error(f"Ошибка отправки части {i}: {e}")
            await bot.send_message(chat_id, f"❌ Часть {i} не отправилась: {str(e)[:100]}")
        finally:
            cleanup_file(part)
        await asyncio.sleep(0.5)


dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✂️ 15 секунд")],
            [KeyboardButton(text="✂️ 30 секунд")],
        ],
        resize_keyboard=True
    )
    await message.answer(
        "👋 Привет!\n\n"
        "Выбери на сколько секунд нарезать видео,\n"
        "потом скинь видео или перешли из канала.",
        reply_markup=kb
    )


@dp.message(F.text == "✂️ 15 секунд")
async def set_15(message: Message):
    user_cut[message.from_user.id] = 15
    await message.answer("✅ Режим: 15 сек\n\nКидай видео или пересылай из канала.", reply_markup=ReplyKeyboardRemove())


@dp.message(F.text == "✂️ 30 секунд")
async def set_30(message: Message):
    user_cut[message.from_user.id] = 30
    await message.answer("✅ Режим: 30 сек\n\nКидай видео или пересылай из канала.", reply_markup=ReplyKeyboardRemove())


@dp.message(F.video | F.document)
async def handle_video(message: Message, bot: Bot):
    user_id = message.from_user.id

    if user_id not in user_cut:
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="✂️ 15 секунд")], [KeyboardButton(text="✂️ 30 секунд")]],
            resize_keyboard=True
        )
        await message.answer("⚠️ Сначала выбери режим нарезки:", reply_markup=kb)
        return

    segment_sec = user_cut[user_id]
    video = message.video or message.document
    title = (message.document.file_name if message.document else None) or f"video_{video.file_unique_id}"
    ext = os.path.splitext(title)[1] or ".mp4"
    local_path = os.path.join(DOWNLOAD_DIR, f"{video.file_unique_id}{ext}")
    file_size_mb = (video.file_size or 0) / (1024 * 1024)

    msg = await message.answer(f"⬇️ Скачиваю {file_size_mb:.0f} MB...")

    try:
        await download_file(video.file_id, local_path)
        actual_mb = os.path.getsize(local_path) / (1024 * 1024)
        logger.info(f"Скачано: {local_path} ({actual_mb:.1f} MB)")

        await msg.edit_text(f"✂️ Нарезаю по {segment_sec} сек...")

        loop = asyncio.get_event_loop()
        parts = await loop.run_in_executor(None, split_video, local_path, segment_sec)

        if not parts:
            raise Exception("ffmpeg не создал файлы — проверь логи")

        total = len(parts)
        await msg.edit_text(f"📤 Отправляю {total} частей...")
        await send_parts(user_id, parts, title, bot)
        await msg.edit_text(f"✅ Готово! {total} частей по {segment_sec} сек.")

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:300]}")
    finally:
        cleanup_file(local_path)


async def main():
    cleanup_all()
    session = AiohttpSession(timeout=600)
    bot = Bot(
        token=BOT_TOKEN,
        session=session,
        base_url=f"{LOCAL_API}/",
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    logger.info("✂️ Бот-нарезчик запущен!")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())



