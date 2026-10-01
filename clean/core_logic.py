import os

from dotenv import load_dotenv

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_LOCAL_ENV = os.path.join(_LIB_DIR, ".env")
_REPO_ENV = os.path.join(_LIB_DIR, "..", ".env")

# Repo root first, then local app/.env overrides (supports clean/.env)
if os.path.isfile(_REPO_ENV):
    load_dotenv(_REPO_ENV)
if os.path.isfile(_LOCAL_ENV):
    load_dotenv(_LOCAL_ENV, override=True)
load_dotenv()


def get_api_key() -> str:
    return os.getenv("MYEMAILVERIFIER_API_KEY", "").strip()
