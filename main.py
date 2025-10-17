import os
from fastapi import FastAPI
from pywa import WhatsApp
from dotenv import load_dotenv

load_dotenv()

PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
TOKEN = os.getenv("WHATSAPP_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
APP_SECRET = os.getenv("META_APP_SECRET")  # optional

app = FastAPI()

# IMPORTANT:
# - Do NOT pass 'callback_url' or 'register_callbacks' with your current pywa version.
# - Your pywa is exposing the webhook at "/" (root). We'll use /healthz for a health check.
wa = WhatsApp(
    phone_id=PHONE_ID,
    token=TOKEN,
    server=app,
    verify_token=VERIFY_TOKEN,
    # If you set APP_SECRET, signature validation will be enabled automatically.
    # If you're not ready to validate signatures yet, uncomment the next line to silence the warning:
    # validate_updates=False,
    app_secret=APP_SECRET,  # harmless if None
)

@app.get("/healthz")
def health():
    return {"status": "ok"}
