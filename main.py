import os
from fastapi import FastAPI
from pywa import WhatsApp
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
TOKEN = os.getenv("WHATSAPP_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
CALLBACK_URL = os.getenv("CALLBACK_URL")

# --- FastAPI app ---
app = FastAPI()

# --- Initialize WhatsApp ---
wa = WhatsApp(
    phone_id=PHONE_ID,
    token=TOKEN,
    server=app,                 # attach FastAPI app
    verify_token=VERIFY_TOKEN,  # Meta webhook verification
    callback_url=CALLBACK_URL,
)

# --- Simple endpoint for status check ---
@app.get("/")
def root():
    return {"status": "✅ PyWa WhatsApp FastAPI server is running!"}

# --- Listener for text messages ---
@wa.on_message()
def handle_message(client: WhatsApp, message):
    print(f"Incoming message from {message.from_user}: {message.text}")
    message.reply_text("Echo: " + (message.text or ""))
