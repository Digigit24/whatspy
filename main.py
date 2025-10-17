# main.py
import os
from fastapi import FastAPI
from pywa import WhatsApp
from dotenv import load_dotenv

load_dotenv()

PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
TOKEN = os.getenv("WHATSAPP_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
CALLBACK_URL = os.getenv("CALLBACK_URL")

APP_ID = os.getenv("META_APP_ID")
APP_SECRET = os.getenv("META_APP_SECRET")

app = FastAPI()

wa = WhatsApp(
    phone_id=PHONE_ID,
    token=TOKEN,
    server=app,
    verify_token=VERIFY_TOKEN,
    callback_url=CALLBACK_URL,   # will auto-register this URL
    app_id=APP_ID,               # <-- required for auto-register
    app_secret=APP_SECRET,       # <-- required for auto-register & signature validation
    # validate_updates=True,     # default is True; good to keep
)
