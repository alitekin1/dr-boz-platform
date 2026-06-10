import os
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(dotenv_path=env_path)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_PLATFORM = os.getenv("BOT_PLATFORM", "bale").strip().lower()
BALE_API_BASE_URL = os.getenv("BALE_API_BASE_URL", "https://tapi.bale.ai/").strip()
if not BALE_API_BASE_URL.endswith("/"):
    BALE_API_BASE_URL += "/"
BALE_FILE_BASE_URL = os.getenv("BALE_FILE_BASE_URL", "https://tapi.bale.ai/file/").strip()
if not BALE_FILE_BASE_URL.endswith("/"):
    BALE_FILE_BASE_URL += "/"
BALE_WALLET_PROVIDER_TOKEN = os.getenv("BALE_WALLET_PROVIDER_TOKEN", "")

TRANSACTIONS_BOT_TOKEN = os.getenv("TRANSACTIONS_BOT_TOKEN", "")
TRANSACTIONS_BOT_ADMIN_CHAT_ID = int(os.getenv("TRANSACTIONS_BOT_ADMIN_CHAT_ID", "0"))
TRANSACTIONS_BOT_PLATFORM = os.getenv("TRANSACTIONS_BOT_PLATFORM", "bale").strip().lower()

NOBITEX_MARKET_STATS_URL = os.getenv("NOBITEX_MARKET_STATS_URL", "https://apiv2.nobitex.ir/market/stats")
NOBITEX_HTTP_TIMEOUT_SECONDS = float(os.getenv("NOBITEX_HTTP_TIMEOUT_SECONDS", "12"))

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./jgpti.db")
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123").strip()
WEB_SEARCH_PROVIDER = os.getenv("WEB_SEARCH_PROVIDER", "exa")
WEB_SEARCH_API_URL = os.getenv("WEB_SEARCH_API_URL", "https://api.exa.ai/search")
WEB_SEARCH_API_KEY = os.getenv("WEB_SEARCH_API_KEY", "")
WEB_SEARCH_MODEL = os.getenv("WEB_SEARCH_MODEL", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "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")

BACKUP_ENABLED = os.getenv("BACKUP_ENABLED", "false").lower() == "true"
BACKUP_INTERVAL_MINUTES = int(os.getenv("BACKUP_INTERVAL_MINUTES", "5"))
BACKUP_MAX_COUNT = int(os.getenv("BACKUP_MAX_COUNT", "6"))
BACKUP_GOOGLE_DRIVE_FOLDER_ID = os.getenv("BACKUP_GOOGLE_DRIVE_FOLDER_ID", "")
BACKUP_GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("BACKUP_GOOGLE_SERVICE_ACCOUNT_JSON", "")

# OpenWebUI sync config
OPENWEBUI_URL = os.getenv("OPENWEBUI_URL", "http://localhost:3000")
OPENWEBUI_SYNC_SECRET = os.getenv("OPENWEBUI_SYNC_SECRET", "")

TITLE_GENERATOR_PROMPT = """### Task:
Generate a concise, 3-5 word title with an emoji summarizing the chat history.
### Guidelines:
- The title should clearly represent the main theme or subject of the conversation.
- Use emojis that enhance understanding of the topic, but avoid quotation marks or special formatting.
- Write the title in the chat's primary language; default to English if multilingual.
- Prioritize accuracy over excessive creativity; keep it clear and simple.
- Output only the final title text.
- Do not use markdown code fences, JSON, explanations, confirmations, or any extra text.
### Output:
your concise title here
### Examples:
- 📉 Stock Market Trends
- 🍪 Perfect Chocolate Chip Recipe
- 🎵 Evolution of Music Streaming
- 💼 Remote Work Productivity
- 🏥 AI in Healthcare
- 🎮 Game Development Insights"""
