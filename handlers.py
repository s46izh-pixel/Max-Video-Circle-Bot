# handlers.py
import logging
import os
import aiohttp
import asyncio
import json
from maxapi.types import MessageCreated
from maxapi.enums.upload_type import UploadType
from maxapi.enums.api_path import ApiPath
from maxapi.enums.http_method import HTTPMethod
from config import TOKEN

# --- Константы ---
MAX_DURATION_SECONDS = 60
INPUT_FILENAME_TPL = "input_media_{}.tmp"
OUTPUT_FILENAME_TPL = "output_video_{}.mp4"

user_media_data = {}

def get_temp_filenames(user_id: str) -> tuple[str, str]:
    return INPUT_FILENAME_TPL.format(user_id), OUTPUT_FILENAME_TPL.format(user_id)

async def cleanup_files(*filenames):
    for filename in filenames:
        if filename and os.path.exists(filename):
            try:
                os.remove(filename)
            except OSError:
                pass

async def start(event: MessageCreated):
    sender = getattr(event.from_user, 'first_name', "Пользователь")
    await event.message.answer(f"Привет, {sender}! 👋\nОтправь видео, и я сделаю кружок в оригинальном качестве.")

async def process_media(event: MessageCreated):
    body = getattr(event.message, 'body', None)
    attachments = getattr(body, 'attachments', [])
    if not attachments: return

    attachment = attachments[0]
    payload = getattr(attachment, 'payload', None)
    file_url = getattr(payload, 'url', getattr(attachment, 'url', getattr(attachment, 'file_url', None)))
    
    if not file_url:
        file_id = getattr(attachment, 'file_id', getattr(payload, 'file_id', None))
        if file_id:
            file_url = f"https://max.pager.dev/api/v1/files/{file_id}/download"
        else:
            await event.message.answer("Не удалось получить видео.")
            return

    user_id = str(getattr(event.from_user, 'user_id', "unknown"))
    input_filename, output_filename = get_temp_filenames(user_id)
    await cleanup_files(input_filename, output_filename)

    sended = await event.message.answer("📥 Загрузка...")
    if not sended or not sended.message: return
    status_msg = sended.message

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url, headers={"Authorization": TOKEN}, timeout=120) as resp:
                if resp.status == 200:
                    with open(input_filename, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(32768):
                            f.write(chunk)
                else:
                    await status_msg.edit(text=f"❌ Ошибка загрузки: {resp.status}")
                    return

        probe_cmd = [
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height', '-of', 'json', input_filename
        ]
        proc = await asyncio.create_subprocess_exec(*probe_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await proc.communicate()
        probe_data = json.loads(stdout.decode())
        
        width = int(probe_data['streams'][0]['width'])
        height = int(probe_data['streams'][0]['height'])

        user_media_data[user_id] = {
            'input_filename': input_filename,
            'status_msg': status_msg,
            'width': width,
            'height': height
        }
        
        await status_msg.edit(text=f"✅ Видео {width}x{height} получено. Напиши 'обработать'.")

    except Exception as e:
        logging.error(f"Prepare error: {e}")
        await event.message.answer("⚠️ Ошибка анализа файла.")

async def message_handler(event: MessageCreated):
    user_id = str(getattr(event.from_user, 'user_id', "unknown"))
    if user_id not in user_media_data: return

    text = getattr(event.message.body, 'text', "").lower().strip()
    if text == 'отмена':
        data = user_media_data.pop(user_id)
        await data['status_msg'].edit(text="Отменено.")
        await cleanup_files(data['input_filename'])
    elif text == 'обработать':
        data = user_media_data.pop(user_id)
        await data['status_msg'].edit(text="⚙️ Конвертирую в кружок (Original Res)...")
        await _perform_conversion(data, event)

async def _perform_conversion(data, event):
    input_filename = data['input_filename']
    status_msg = data['status_msg']
    user_id = str(getattr(event.from_user, 'user_id', "unknown"))
    _, output_filename = get_temp_filenames(user_id)

    try:
        # Сохраняем оригинальное разрешение (минимум из сторон для квадрата)
        size = min(data['width'], data['height'])
        
        # Строгий квадрат H.264 Baseline без B-кадров
        vf = f"crop='min(iw,ih)':'min(iw,ih)',scale={size}:{size},format=yuv420p"
        
        cmd = [
            'ffmpeg', '-y', '-i', input_filename,
            '-t', str(MAX_DURATION_SECONDS),
            '-vf', vf,
            '-c:v', 'libx264', '-profile:v', 'baseline', '-level', '3.0',
            '-crf', '18', '-preset', 'slow',
            '-bf', '0',
            '-c:a', 'aac', '-b:a', '192k',
            '-movflags', '+faststart',
            output_filename
        ]
        
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await proc.communicate()

        await status_msg.edit(text="🚀 Отправка кружка в MAX...")
        
        upload_info = await event.bot.get_upload_url(UploadType.VIDEO)
        await event.bot.upload_file(url=upload_info.url, path=output_filename, type=UploadType.VIDEO)
        
        chat_id = getattr(event.chat, 'chat_id', None)
        target_user_id = getattr(event.from_user, 'user_id', None)
        
        params = {}
        if chat_id: params["chat_id"] = chat_id
        elif target_user_id: params["user_id"] = target_user_id

        # ФИНАЛЬНАЯ СТРУКТУРА: флаги в payload и в корне вложения
        payload = {
            "attachments": [
                {
                    "type": "video",
                    "payload": {
                        "token": upload_info.token,
                        "format": "mug",
                        "quickVideo": True
                    },
                    "quickVideo": True
                }
            ]
        }
        
        # Исправленный вызов: добавляем is_return_raw=True чтобы избежать ошибки NoneType
        await event.bot.request(
            method=HTTPMethod.POST,
            path=ApiPath.MESSAGES,
            params=params,
            json=payload,
            is_return_raw=True
        )
        
        await status_msg.delete()

    except Exception as e:
        logging.error(f"Final error: {e}", exc_info=True)
        await status_msg.edit(text=f"❌ Ошибка отправки: {str(e)}")
    finally:
        await cleanup_files(input_filename, output_filename)
