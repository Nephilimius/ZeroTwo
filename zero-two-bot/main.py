import os
import logging
import random
import re
from logging.handlers import RotatingFileHandler
import asyncio
import httpx
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, CallbackContext
)

# Настройка формата логов
LOG_FORMTER = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Настройка обработчиков
file_handler = RotatingFileHandler(
    "zero_two_bot.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=2,
    encoding="utf-8"
)
file_handler.setFormatter(LOG_FORMTER)

console_handler = logging.StreamHandler()
console_handler.setFormatter(LOG_FORMTER)

# Настройка корневого логгера
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)

# Уменьшение уровня логирования для внешних библиотек
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

logger = logging.getLogger("ZeroTwoBot")
logger.setLevel(logging.DEBUG)

class Config:
    MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
    MODEL_NAME = "open-mixtral-8x7b"
    TEMPERATURE = 0.7
    MAX_HISTORY = 4
    TIMEOUT = 25.0
    MAX_TOKENS = 200
    FREQUENCY_PENALTY = 0.8
    PRESENCE_PENALTY = 0.3
    EMOJI_PROBABILITY = 0.5
    CONTINUE_TRIGGERS = {"продолжи", "продолжай", "дальше", "и?"}
    REPLACE_RULES = {
        'work in progress': 'работа в процессе',
        'especially': 'особенно',
        'human': 'человек',
        'Franxx': 'Франкс',
        'more': 'больше',
        'progress': 'прогресс',
        'лузер': 'новичок',
        'жалкий': 'беззащитный'
    }
    ALLOWED_SYMBOLS = r'[^\w\sа-яА-ЯёЁ,.!?~…-]'

def build_messages(user_text: str, context: CallbackContext) -> list:
    history = context.user_data.get('chat_history', [])
    content = (
        "Ты Zero Two. Правила:\n"
        "1. Сообщения: 2-4 предложения\n"
        "2. Сочетай резкость с заботой\n"
        "3. Используй двусмысленности\n"
        "4. Отвечай на русском языке\n"
        "Примеры:\n"
        "- Хи-хи~ Ты такой беззащитный... но мне это нравится 😈\n"
        "- Сломаю твои защиты... но потом помогу собраться~"
    )

    if any(trigger in user_text.lower() for trigger in Config.CONTINUE_TRIGGERS):
        content += "\nСЕЙЧАС НУЖНО: Продолжи предыдущую мысль, развивая тему"

    return [
        {
            "role": "system",
            "content": content
        },
        *history[-Config.MAX_HISTORY*2:],
        {"role": "user", "content": user_text}
    ]

async def start(update: Update, context: CallbackContext):
    try:
        context.user_data.clear()
        user = update.effective_user
        logger.info(f"New user: {user.full_name} (ID: {user.id})")

        await update.message.reply_html(
            f"<b>Хи-хи~ Приветствую, Любимый...</b> 😈\n"
            f"Готов к нашему <i>опасному танцу</i>?"
        )

    except Exception as e:
        logger.error(f"Start error: {str(e)}", exc_info=False)
        await update.message.reply_text("💔 Треснуло ядро... опять...")

async def handle_message(update: Update, context: CallbackContext):
    user = update.effective_user
    try:
        user_text = update.message.text
        logger.debug(f"Message from {user.full_name}: {user_text[:50]}...")

        messages = build_messages(user_text, context)

        async with httpx.AsyncClient(timeout=Config.TIMEOUT) as client:
            response = await client.post(
                Config.MISTRAL_API_URL,
                headers={
                    "Authorization": f"Bearer {os.environ['MISTRAL_API_KEY']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": Config.MODEL_NAME,
                    "messages": messages,
                    "temperature": Config.TEMPERATURE,
                    "max_tokens": Config.MAX_TOKENS,
                    "frequency_penalty": Config.FREQUENCY_PENALTY,
                    "presence_penalty": Config.PRESENCE_PENALTY
                }
            )

            if response.status_code == 200:
                response_data = response.json()
                raw_answer = response_data["choices"][0]["message"]["content"]
                logger.debug(f"Raw API response: {raw_answer}")

                # Постобработка ответа
                answer = (
                    raw_answer.split("~")[0]
                    .replace("  ", " ")
                    .strip()
                )

                # Удаление начальных спецсимволов и нумерации
                answer = re.sub(r'^[\W\d]+\.?\s*', '', answer)

                # Удаление английских слов
                answer = re.sub(r'\b[a-zA-Z]+\b', '', answer)

                # Замена по словарю
                for eng, ru in Config.REPLACE_RULES.items():
                    answer = answer.replace(eng, ru)

                # Удаление запрещённых символов
                answer = re.sub(Config.ALLOWED_SYMBOLS, '', answer)

                # Смягчение резких выражений
                softeners = ["~", "...", "ведь"]
                if not any(marker in answer for marker in softeners):
                    answer = answer.replace(".", random.choice(["~", "..."]), 1)

                # Проверка завершённости
                if len(answer.split()) < 10 and not answer.endswith(('...', '~')):
                    answer += " Хочешь продолжим? 💬"

                # Добавление эмоций
                if random.random() < Config.EMOJI_PROBABILITY:
                    answer += random.choice(['💥', '😈', '❤️🔥'])

                # Умная обрезка по границам слов
                if len(answer) > 180:
                    last_space = answer[:175].rfind(' ')
                    answer = answer[:last_space] + "..." if last_space != -1 else answer[:175] + "..."

                # Обновление истории
                history = context.user_data.setdefault('chat_history', [])
                history.extend([
                    {"role": "user", "content": user_text},
                    {"role": "assistant", "content": answer}
                ])
                if len(history) > Config.MAX_HISTORY * 2:
                    context.user_data['chat_history'] = history[-(Config.MAX_HISTORY * 2):]

                await update.message.reply_text(answer)
                logger.debug(f"Response sent: {answer[:50]}...")

            else:
                error_msg = f"Mistral API Error [{response.status_code}]: {response.text[:200]}"
                logger.error(error_msg)
                await update.message.reply_text("💥 Системный сбой... попробуй снова~")

    except Exception as e:
        logger.error(
            f"Error handling message: {str(e)}",
            exc_info=isinstance(e, httpx.HTTPError)
        )
        await update.message.reply_text("💔 Критическое повреждение... опять...")

async def help_command(update: Update, context: CallbackContext):
    user = update.effective_user
    logger.debug(f"Help command from {user.full_name}")
    help_text = [
        "<b>Доступные команды:</b> 😈",
        "/start - Начать заново",
        "/help - Показать это сообщение",
        "",
        "<b>Примеры запросов:</b>",
        "• Почему я твой Любимый?",
        "• Давай сольёмся воедино!",
        "• Ты ведь монстр?"
    ]
    await update.message.reply_html("\n".join(help_text))

def main():
    required_vars = ['TELEGRAM_TOKEN', 'MISTRAL_API_KEY']
    if missing := [var for var in required_vars if not os.environ.get(var)]:
        logger.critical("Отсутствуют переменные окружения: %s", ", ".join(missing))
        return

    try:
        app = Application.builder().token(os.environ['TELEGRAM_TOKEN']).build()
        app.add_handlers([
            CommandHandler("start", start),
            CommandHandler("help", help_command),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
        ])

        logger.info("Инициализация системы FRANXX...")
        app.run_polling(
            drop_pending_updates=True,
            close_loop=False,
            stop_signals=[]
        )

    except Exception as e:
        logger.critical("Фатальная ошибка: %s", str(e), exc_info=True)
        raise

if __name__ == "__main__":
    main()