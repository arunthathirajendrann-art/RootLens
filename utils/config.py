import os
from dotenv import load_dotenv

load_dotenv()

# Gemini configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("LLM_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.6-flash"))

# Path variables
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
PAST_INCIDENTS_PATH = os.path.join(DATA_DIR, "past_incidents.json")

def get_llm_config() -> dict:
    return {
        "provider": "gemini",
        "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
        "model": os.getenv("LLM_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash")),
    }

