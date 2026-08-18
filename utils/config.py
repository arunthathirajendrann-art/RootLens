import os
from dotenv import load_dotenv

load_dotenv()

# Gemini configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("LLM_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.6-flash"))

# Path variables
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
PAST_INCIDENTS_PATH = os.path.join(DATA_DIR, "past_incidents.json")

def is_mock_mode() -> bool:
    raw_mock = os.getenv("LLM_MOCK_MODE", "").lower()
    if raw_mock in ("true", "1", "yes"):
        return True
    if not os.getenv("GEMINI_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        return True
    return False

def is_gemini_active() -> bool:
    return bool(os.getenv("GEMINI_API_KEY")) and not is_mock_mode()

def get_llm_config() -> dict:
    return {
        "mock_mode": is_mock_mode(),
        "provider": os.getenv("LLM_PROVIDER", "gemini").lower(),
        "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
        "model": os.getenv("LLM_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.6-flash")),
    }

