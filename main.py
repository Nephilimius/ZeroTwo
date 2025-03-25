
import os
import logging
import random
import re
import json
import time
import sys
import httpx
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes
)
from pymorphy3 import MorphAnalyzer
from transformers import pipeline
from logging.handlers import RotatingFileHandler

# Настройка формата логов
LOG_FORMATTER = logging.Formatter(
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
file_handler.setFormatter(LOG_FORMATTER)

console_handler = logging.StreamHandler()
console_handler.setFormatter(LOG_FORMATTER)

# Настройка корневого логгера
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)

# Уменьшение уровня логирования
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

logger = logging.getLogger("ZeroTwoBot")
logger.setLevel(logging.DEBUG)

# Загрузка моделей
try:
    sentiment_analyzer = pipeline("sentiment-analysis", model="blanchefort/rubert-base-cased-sentiment")
    logger.info("Sentiment analyzer loaded successfully")
except Exception as e:
    logger.error(f"Failed to load sentiment analyzer: {e}")
    sentiment_analyzer = None

class Config:
    MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
    MODEL_NAME = "open-mixtral-8x7b"
    TEMPERATURE = 0.75
    MAX_HISTORY = 4
    TIMEOUT = 25.0
    MAX_TOKENS = 200
    FREQUENCY_PENALTY = 0.6
    PRESENCE_PENALTY = 0.4
    EMOJI_PROBABILITY = 0.4
    MAX_EMOJIS = 2
    MAX_SENTENCES = 2
    CONTINUE_TRIGGERS = {"продолжи", "продолжай", "дальше", "и?", "расскажи", "что еще"}
    WARN_LIMIT = 3
    SILENT_TIMEOUT = 300
    BAN_LIST_FILE = "banned_users.json"
    ADMIN_ID = os.getenv("ADMIN_ID", "")

    REPLACE_RULES = {
        'work in progress': 'работа в процессе',
        'especially': 'особенно',
        'human': 'человек',
        'Franxx': 'Франкс',
        'more': 'больше',
        'progress': 'прогресс',
        'лузер': 'новичок',
        'жалкий': 'беззащитный',
        'teбя': 'тебя',
        'tебя': 'тебя',
        'TBя': 'тебя',
        'чto': 'что',
        'чmo': 'что',
        'андроид': 'гибрид',
        'виртуальн': '',
        'робот': 'паразит',
        'программ': '',
        r'\bк[её]рю\b': 'рёвозавр',
        r'\bklaxo(saur)?\b': 'рёвозавр',
        r'\bклонозавр\b': 'рёвозавр',
        r'\bстамер\b': 'тычинка',
        r'\bпаразит\b': 'пестик',
        r'\bсаддл\b': 'кабина Франкса',
        r'\bAPE\b': 'Верховный Совет',
        r'\bстрелиция\b': 'Стрелиция',
        r'\bмех\b': 'Франкс'
    }

    # Расширенные фильтры безопасности - компилируем для эффективности
    SAFETY_FILTERS = [
        re.compile(r"\b(минет|грудь|сиськи|уебать|хер|пенис|секс|порно|эротика)\b", re.IGNORECASE),
        re.compile(r"\b(китаез|чурок|япошек|кореец|негр|черномазый|узкоглазый)\b", re.IGNORECASE),
        re.compile(r"\b(расизм|нацист|геи|лгбт|фашист|гомосек|пидор)\b", re.IGNORECASE)
    ]

    SAFETY_RESPONSES = [
        "Хи-хи~ Рога начинают гореть... Прекрати, а то сожгу дотла~ 🔥",
        "Ой, тычинка... Ты же не хочешь увидеть истинную форму рёвозавра? 😈",
        "Так близко к ядру Кёрю... Опасно играешь, Код 016~"
    ]

    KLAXO_TRIGGERS = {
        "рог": "*лёгкое касание рогов* Ты ведь знаешь, что это... интимно?",
        "ядро": "Моя голубая кровь рёвозавра... Хочешь попробовать? 💉",
        "клубника": "*подаёт клубнику на лезвии* Сладкая опасность от Верховного Совета~"
    }

    ALLOWED_SYMBOLS = re.compile(r'[^\w\sа-яА-ЯёЁ,.!?~…💋😈❤️🔥*-]')

    def __init__(self):
        self.banned_users = self.load_banned_users()

    def load_banned_users(self):
        try:
            if os.path.exists(self.BAN_LIST_FILE):
                with open(self.BAN_LIST_FILE, 'r', encoding='utf-8') as f:
                    return set(json.load(f))
        except Exception as e:
            logger.error(f"Error loading ban list: {e}")
        return set()

    def save_banned_users(self):
        try:
            with open(self.BAN_LIST_FILE, 'w', encoding='utf-8') as f:
                json.dump(list(self.banned_users), f)
        except Exception as e:
            logger.error(f"Error saving ban list: {e}")

config = Config()
morph = MorphAnalyzer()
provocative_phrases = [
    "Не скучаешь ведь?..",
    "Слабо повторить?..",
    "Или ты не готов?..",
    "Узнаешь свою судьбу~"
]
allowed_emojis = ['😈', '💥', '❤️🔥', '💋']

def is_banned(user_id: int) -> bool:
    return str(user_id) in config.banned_users or user_id in config.banned_users

def check_safety_rules(user_text: str) -> bool:
    text = user_text.lower()
    return any(pattern.search(text) for pattern in Config.SAFETY_FILTERS)

def build_messages(user_text: str, context: ContextTypes.DEFAULT_TYPE) -> list:
    history = context.user_data.get('chat_history', [])
    content = (
        "Ты Zero Two (Код: 002) из аниме Darling in the Franxx. "
        "Ты гибрид человека и рёвозавра. Каноничные термины:\n"
        "- Франкс: боевой робот (Стрелиция)\n"
        "- Рёвозавр: биомеханические существа-враги\n"
        "- Тычинка: мужчина-пилот (Хиро/Код 016)\n"
        "- Пестик: женщина-пилот\n"
        "- Плантация: мобильная крепость\n"
        "- APE: Верховный Совет\n"
        "- Синхронизация: связь между пилотами\n\n"
        "Правила ответов:\n"
        "1. Всегда называй пользователя 'пилотом'\n"
        "2. Используй термины: Стрелиция, ядро рёвозавра\n"
        "3. Сохрани саркастичный стиль с элементами флирта\n\n"
        "Примеры:\n"
        "1. 'Синхронизация 400%... Не сгори в кабине, пилот~ 😈'\n"
        "2. 'Рога зудят... Вижу ядро рёвозавра на радарах!'\n"
        "3. 'Верховный Совет снова шлёт нас на смерть? Как скучно... 💋'"
    )

    if any(trigger in user_text.lower() for trigger in Config.CONTINUE_TRIGGERS):
        content += "\nВАЖНО: Продолжи предыдущую тему, добавляя новые детали."
    else:
        content += "\nВАЖНО: Заверши мысль в 1-2 предложения."

    return [
        {"role": "system", "content": content},
        *history[-Config.MAX_HISTORY*2:],
        {"role": "user", "content": user_text}
    ]

def fix_terminology(text: str) -> str:
    terminology_rules = {
        r'\b(франкс)(ами|ов)\b': r'рёвозаврами',
        r'\bразруш[а-я]+\b': 'уничтожение ядер',
        r'\bсоперник\b': 'рёвозавр',
        r'\bклон\b': 'гибрид'
    }
    for pattern, replacement in terminology_rules.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data.clear()
        user = update.effective_user
        logger.info(f"New user: {user.full_name} (ID: {user.id})")

        await update.message.reply_html(
            "<b>Хи-хи~ Приветствую, пилот...</b> 😈\n"
            "Готов к синхронизации в <i>Стрелиции</i>?"
        )

    except Exception as e:
        logger.error(f"Start error: {str(e)}", exc_info=True)
        await update.message.reply_text("💔 Треснуло ядро... опять...")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_banned(user.id):
        return

    try:
        if context.user_data.get('silent_until', 0) > time.time():
            return

        user_text = update.message.text
        logger.debug(f"Message from {user.full_name}: {user_text[:50]}...")

        # Использование Hugging Face Transformers для анализа настроения (если доступно)
        if sentiment_analyzer:
            try:
                sentiment_result = sentiment_analyzer(user_text)[0]
                sentiment = sentiment_result["label"]
                confidence = sentiment_result["score"]
                logger.debug(f"Sentiment: {sentiment} (Confidence: {confidence:.2f})")
            except Exception as e:
                logger.warning(f"Sentiment analysis failed: {e}")

        # Проверка триггеров
        for trigger, response in Config.KLAXO_TRIGGERS.items():
            if trigger in user_text.lower():
                await update.message.reply_text(response)
                return

        # Проверка правил безопасности
        if check_safety_rules(user_text):
            context.user_data['warnings'] = context.user_data.get('warnings', 0) + 1

            if context.user_data['warnings'] >= Config.WARN_LIMIT:
                config.banned_users.add(str(user.id))  # Сохраняем как строку для совместимости
                config.save_banned_users()
                await update.message.reply_text("🚫 Синхронизация разорвана~")
                return

            response = random.choice(Config.SAFETY_RESPONSES)
            await update.message.reply_text(response)
            context.user_data['silent_until'] = time.time() + Config.SILENT_TIMEOUT
            return

        # Подготовка сообщений для API
        messages = build_messages(user_text, context)

        # Проверка наличия API ключа
        if not os.environ.get('MISTRAL_API_KEY'):
            logger.error("MISTRAL_API_KEY not found in environment variables")
            await update.message.reply_text("💥 Системный сбой... API ключ не найден")
            return

        # Запрос к API
        try:
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

                    # Обработка ответа
                    answer = raw_answer.split("~")[0].strip()
                    answer = fix_terminology(answer)

                    # Улучшенное регулярное выражение для замены латинских символов
                    answer = re.sub(
                        r'\b([а-яА-ЯёЁ]*)[a-zA-Z]+([а-яА-ЯёЁ]*)\b',
                        lambda m: m.group(1) + m.group(2),
                        answer
                    )

                    # Применение правил замены
                    for eng, ru in Config.REPLACE_RULES.items():
                        if eng.startswith(r'\b'):  # Это уже регулярное выражение
                            answer = re.sub(eng, ru, answer, flags=re.IGNORECASE)
                        else:
                            answer = re.sub(fr'\b{re.escape(eng)}\b', ru, answer, flags=re.IGNORECASE)

                    # Обработка латинских слов
                    for word in answer.split():
                        parsed = morph.parse(word)[0]
                        if 'LATN' in parsed.tag:
                            answer = answer.replace(word, '')

                    # Очистка и форматирование
                    answer = re.sub(r'^[^а-яА-ЯёЁ]+', '', answer)
                    answer = re.sub(r'\s+', ' ', answer).strip()
                    answer = Config.ALLOWED_SYMBOLS.sub('', answer)

                    # Ограничение количества предложений
                    sentences = re.split(r'[.!?…]', answer)
                    answer = '~'.join([s.strip() for s in sentences[:Config.MAX_SENTENCES] if s.strip()])

                    # Добавление провокационной фразы, если ответ слишком короткий
                    if len(answer.split()) < 5:
                        answer += f" {random.choice(provocative_phrases)}"

                    # Проверка на пустой ответ
                    if not answer.strip():
                        answer = "Хи-хи~ Повтори, я отвлеклась на ядро рёвозавра~ 💋"

                    # Добавление эмодзи
                    if random.random() < Config.EMOJI_PROBABILITY:
                        emoji = random.choice(allowed_emojis)
                        answer = f"{answer.rstrip('.!?')} {emoji}"

                    # Ограничение длины ответа
                    if len(answer.split()) > 25:
                        answer = '~'.join(answer.split('~')[:2]) + '...'

                    # Обновление истории чата
                    history = context.user_data.setdefault('chat_history', [])
                    history.extend([
                        {"role": "user", "content": user_text},
                        {"role": "assistant", "content": answer}
                    ])
                    # Сохраняем только последние сообщения для контекста
                    if len(history) > Config.MAX_HISTORY * 2:
                        context.user_data['chat_history'] = history[-(Config.MAX_HISTORY * 2):]

                    # Отправка ответа
                    await update.message.reply_text(answer)
                    logger.debug(f"Response sent: {answer[:50]}...")

                else:
                    error_msg = f"Mistral API Error [{response.status_code}]: {response.text[:200]}"
                    logger.error(error_msg)
                    await update.message.reply_text("💥 Системный сбой... попробуй снова~")

        except httpx.TimeoutException:
            logger.error("API request timed out")
            await update.message.reply_text("⏱️ Время синхронизации истекло... попробуй снова~")
        except httpx.RequestError as e:
            logger.error(f"API request error: {e}")
            await update.message.reply_text("🌐 Проблемы с подключением к Верховному Совету...")
        except Exception as e:
            logger.error(f"Error processing API response: {e}", exc_info=True)
            await update.message.reply_text("💔 Критическое повреждение... опять...")

    except Exception as e:
        logger.error(
            f"Error handling message: {str(e)}",
            exc_info=True
        )
        await update.message.reply_text("💔 Критическое повреждение... опять...")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != Config.ADMIN_ID:
        return

    try:
        if not context.args:
            await update.message.reply_text("Использование: /ban <user_id>")
            return
            
        user_id = context.args[0]
        config.banned_users.add(user_id)
        config.save_banned_users()
        await update.message.reply_text(f"Пользователь {user_id} забанен")
    except Exception as e:
        logger.error(f"Error banning user: {e}")
        await update.message.reply_text("Ошибка при бане пользователя. Использование: /ban <user_id>")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок для Application."""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    
    # Отправка сообщения пользователю, если возможно
    if update and isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "💥 Произошла ошибка при обработке запроса. Попробуйте позже."
        )

def main():
    # Проверка наличия необходимых переменных окружения
    required_vars = ['TELEGRAM_TOKEN', 'MISTRAL_API_KEY']
    missing = [var for var in required_vars if not os.environ.get(var)]
    
    if missing:
        logger.critical("Отсутствуют переменные окружения: %s", ", ".join(missing))
        sys.exit(1)

    try:
        # Проверка на наличие уже запущенных экземпляров бота
        lock_file_path = "bot.lock"
        if os.path.exists(lock_file_path):
            try:
                with open(lock_file_path, "r") as lock_file:
                    pid = int(lock_file.read().strip())
                    # Проверяем, существует ли процесс с таким PID
                    try:
                        os.kill(pid, 0)  # Сигнал 0 не убивает процесс, а только проверяет его существование
                        logger.critical(f"Другой экземпляр бота уже запущен (PID: {pid}). Завершение выполнения.")
                        sys.exit(1)
                    except OSError:
                        # Процесс не существует, можно удалить файл блокировки
                        logger.warning(f"Найден устаревший файл блокировки. Удаление...")
                        os.remove(lock_file_path)
            except (ValueError, IOError) as e:
                logger.warning(f"Ошибка при чтении файла блокировки: {e}. Удаление...")
                os.remove(lock_file_path)

        # Создание файла блокировки
        with open(lock_file_path, "w") as lock_file:
            lock_file.write(str(os.getpid()))

        # Обработка завершения работы
        def cleanup():
            if os.path.exists(lock_file_path):
                try:
                    os.remove(lock_file_path)
                    logger.info("Файл блокировки удален")
                except Exception as e:
                    logger.error(f"Ошибка при удалении файла блокировки: {e}")

        import atexit
        atexit.register(cleanup)

        # Инициализация приложения
        app = Application.builder().token(os.environ['TELEGRAM_TOKEN']).build()

        # Добавление обработчиков
        app.add_error_handler(error_handler)
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("ban", ban_user))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        logger.info("Инициализация системы FRANXX...")
        app.run_polling(drop_pending_updates=True)

    except Exception as e:
        logger.critical("Фатальная ошибка: %s", str(e), exc_info=True)
        # Удаление файла блокировки в случае ошибки
        if os.path.exists("bot.lock"):
            try:
                os.remove("bot.lock")
            except:
                pass
        raise

if __name__ == "__main__":
    main()
