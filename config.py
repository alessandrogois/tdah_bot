import os
from dotenv import load_dotenv

load_dotenv()

# Obrigatórios — defina no .env
TOKEN = os.getenv("TELEGRAM_TOKEN", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Seu chat_id do Telegram (rode /start e veja os logs, ou use @userinfobot)
CHAT_ID = int(os.getenv("CHAT_ID", "0"))

# Fuso horário (lista: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)
TIMEZONE = os.getenv("TIMEZONE", "America/Sao_Paulo")

# Caminho do banco de dados SQLite
DB_PATH = os.getenv("DB_PATH", "bot_data.db")

# Validação mínima
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN não definido no .env")
if not GROQ_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY não definido no .env")
if not CHAT_ID:
    raise ValueError("CHAT_ID não definido no .env")
