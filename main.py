# main.py
import asyncio
import logging
from maxapi import Bot, Dispatcher, F
from maxapi.filters.command import Command
from config import TOKEN
from handlers import start, process_media, message_handler

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def main():
    """Запускает бота."""
    logger.info(f"Запуск бота с токеном: {TOKEN}")
    logger.info("Проверка конфигурации...")

    bot = Bot(TOKEN)
    dp = Dispatcher()
    
    # Регистрация обработчиков через декораторы (вызовы объекта Event)
    dp.message_created(Command("start"))(start)
    
    # Обработка медиа
    dp.message_created(F.message.body.attachments)(process_media)
    
    # Обработка текстовых сообщений
    dp.message_created(F.message.body.text)(message_handler)

    logger.info("Бот запущен и слушает обновления...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
