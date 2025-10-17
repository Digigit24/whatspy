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

app = FastAPI()

wa = WhatsApp(
    phone_id=PHONE_ID,
    token=TOKEN,
    server=app,
    verify_token=VERIFY_TOKEN,
    # leave callback_url in .env for later, but don't auto-register yet
    register_callbacks=False,   # <— key line
    validate_updates=False      # optional: silence signature warnings until app_secret is added
)

@app.get("/")
def root():
    return {"status": "✅ PyWa WhatsApp FastAPI server is running!"}
