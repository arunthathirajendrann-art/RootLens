import os
from dotenv import load_dotenv

load_dotenv()

# Gemini configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# Path variables
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
PAST_INCIDENTS_PATH = os.path.join(DATA_DIR, "past_incidents.json")

def is_gemini_active() -> bool:
    return bool(GEMINI_API_KEY)
