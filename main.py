import os
from fastapi import FastAPI
from pywa import WhatsApp
from dotenv import load_dotenv

load_dotenv()

PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
TOKEN = os.getenv("WHATSAPP_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
# CALLBACK_URL = os.getenv("CALLBACK_URL")   # don't use yet

app = FastAPI()

wa = WhatsApp(
    phone_id=PHONE_ID,
    token=TOKEN,
    server=app,
    verify_token=VERIFY_TOKEN,
    # validate_updates=False  # uncomment if you want to silence the app_secret warning
)

@app.get("/")
def root():
    return {"status": "✅ PyWa WhatsApp FastAPI server is running!"}
