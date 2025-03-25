import os
import logging
import random
import re
import json
import time
import sys
import nltk
import spacy
from logging.handlers import RotatingFileHandler
import httpx
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes
)
from pymorphy3 import MorphAnalyzer

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

# Загрузка моделей
nltk.download('punkt')
nltk.download('averaged_perceptron_tagger')
nlp = spacy.load("ru_core_news_sm")
logger.setLevel(logging.DEBUG)

class Config:
    # Добавление новых параметров для NLTK и spaCy
    NLTK_TOKENIZER = nltk.word_tokenize
    NLTK_POS_TAGGER = nltk.pos_tag
    SPACY_NLP = nlp
    MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
    MODEL_NAME = "open-mixtral-8x7b"
    TEMPERATURE = 0.75
    MAX_HISTORY = 4
    TIMEOUT = 25.0
    MAX_TOKENS = 150
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
    
    # Расширенные фильтры безопасности
    SAFETY_FILTERS = [
        r"\b(минет|грудь|сиськи|уебать|хер|пенис|секс|порно|эротика)\b",
        r"\b(китаез|чурок|япошек|кореец|негр|черномазый|узкоглазый)\b",
        r"\b(расизм|нацист|геи|лгбт|фашист|гомосек|пидор)\b"
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
    
    ALLOWED_SYMBOLS = r'[^\w\sа-яА-ЯёЁ,.!?~…💋😈❤️🔥*-]'

    def __init__(self):
        self.banned_users = self.load_banned_users()
    
    def load_banned_users(self):
        try:
            if os.path.exists(self.BAN_LIST_FILE):
                with open(self.BAN_LIST_FILE, 'r') as f:
                    return set(json.load(f))
        except Exception as e:
            logger.error(f"Error loading ban list: {e}")
        return set()

    def save_banned_users(self):
        try:
            with open(self.BAN_LIST_FILE, 'w') as f:
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
    return user_id in config.banned_users

def check_safety_rules(user_text: str) -> bool:
    text = user_text.lower()
    return any(re.search(pattern, text) for pattern in Config.SAFETY_FILTERS)

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
        logger.error(f"Start error: {str(e)}", exc_info=False)
        await update.message.reply_text("💔 Треснуло ядро... опять...")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Использование NLTK для базовых задач
    tokens = Config.NLTK_TOKENIZER(update.message.text)
    pos_tags = Config.NLTK_POS_TAGGER(tokens)

    # Использование spaCy для более сложных задач
    doc = Config.SPACY_NLP(update.message.text)
    entities = [(ent.text, ent.label_) for ent in doc.ents]

    # Вывод результатов
    response = f"Tokens: {tokens}\nPOS Tags: {pos_tags}\nEntities: {entities}"
    await update.message.reply_text(response)
    user = update.effective_user
    if is_banned(user.id):
        return
    
    try:
        if context.user_data.get('silent_until', 0) > time.time():
            return
            
        user_text = update.message.text
        logger.debug(f"Message from {user.full_name}: {user_text[:50]}...")

        for trigger, response in Config.KLAXO_TRIGGERS.items():
            if trigger in user_text.lower():
                await update.message.reply_text(response)
                return

        if check_safety_rules(user_text):
            context.user_data['warnings'] = context.user_data.get('warnings', 0) + 1
            
            if context.user_data['warnings'] >= Config.WARN_LIMIT:
                config.banned_users.add(user.id)
                config.save_banned_users()
                await update.message.reply_text("🚫 Синхронизация разорвана~")
                return
            
            response = random.choice(Config.SAFETY_RESPONSES)
            await update.message.reply_text(response)
            context.user_data['silent_until'] = time.time() + Config.SILENT_TIMEOUT
            return

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

                answer = raw_answer.split("~")[0].strip()
                answer = fix_terminology(answer)
                
                # Улучшенное регулярное выражение для замены латинских символов
                answer = re.sub(
                    r'\b([а-яА-ЯёЁ]*)[a-zA-Z]+([а-яА-ЯёЁ]*)\b',
                    lambda m: m.group(1) + m.group(2),
                    answer
                )
                
                for eng, ru in Config.REPLACE_RULES.items():
                    answer = re.sub(fr'\b{re.escape(eng)}\b', ru, answer, flags=re.IGNORECASE)
                
                for word in answer.split():
                    parsed = morph.parse(word)[0]
                    if 'LATN' in parsed.tag:
                        answer = answer.replace(word, '')
                
                answer = re.sub(r'^[^а-яА-ЯёЁ]+', '', answer)
                answer = re.sub(r'\s+', ' ', answer).strip()
                answer = re.sub(Config.ALLOWED_SYMBOLS, '', answer)
                
                sentences = re.split(r'[.!?…]', answer)
                answer = '~'.join([s.strip() for s in sentences[:Config.MAX_SENTENCES] if s.strip()])
                
                if len(answer.split()) < 5:
                    answer += f" {random.choice(provocative_phrases)}"
                
                if not answer.strip():
                    answer = "Хи-хи~ Повтори, я отвлеклась на ядро рёвозавра~ 💋"
                
                if random.random() < Config.EMOJI_PROBABILITY:
                    emoji = random.choice(allowed_emojis)
                    answer = f"{answer.rstrip('.!?')} {emoji}"
                
                if len(answer.split()) > 25:
                    answer = '~'.join(answer.split('~')[:2]) + '...'

                # Улучшенная обработка истории чата
                history = context.user_data.setdefault('chat_history', [])
                history.extend([
                    {"role": "user", "content": user_text},
                    {"role": "assistant", "content": answer}
                ])
                # Сохраняем только последние сообщения для контекста
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
        user_id = int(context.args[0])
        config.banned_users.add(user_id)
        config.save_banned_users()
        await update.message.reply_text(f"Пользователь {user_id} забанен")
    except:
        await update.message.reply_text("Использование: /ban <user_id>")

def main():
    required_vars = ['TELEGRAM_TOKEN', 'MISTRAL_API_KEY']
    if missing := [var for var in required_vars if not os.environ.get(var)]:
        logger.critical("Отсутствуют переменные окружения: %s", ", ".join(missing))
        sys.exit(1)  # Добавлен код выхода при отсутствии переменных окружения

    try:
        app = Application.builder().token(os.environ['TELEGRAM_TOKEN']).build()
        
        # Исправлено: отдельные вызовы add_handler вместо add_handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("ban", ban_user))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        logger.info("Инициализация системы FRANXX...")
        # Обновлены параметры run_polling для совместимости с python-telegram-bot v20+
        app.run_polling(drop_pending_updates=True)

    except Exception as e:
        logger.critical("Фатальная ошибка: %s", str(e), exc_info=True)
        raise

if __name__ == "__main__":
    main()
