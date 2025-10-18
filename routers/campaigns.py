# routers/campaigns.py
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from collections import deque

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import MAX_BUFFER

log = logging.getLogger("whatspy.campaigns")

router = APIRouter()
wa_client = None

# Campaign storage
campaigns_buffer: deque = deque(maxlen=MAX_BUFFER)

def init_wa_client(client):
    """Initialize WhatsApp client"""
    global wa_client
    wa_client = client

# ────────────────────────────────
# Models
# ────────────────────────────────
class BroadcastIn(BaseModel):
    """Broadcast message to multiple recipients"""
    recipients: List[str] = Field(..., min_items=1, description="List of phone numbers")
    message: str = Field(..., min_length=1, max_length=4096)
    campaign_name: Optional[str] = Field(None, description="Optional campaign name for tracking")

class CampaignStatus(BaseModel):
    """Campaign status response"""
    campaign_id: str
    campaign_name: Optional[str]
    total_recipients: int
    sent: int
    failed: int
    timestamp: str
    results: List[Dict[str, Any]]

# ────────────────────────────────
# Endpoints
# ────────────────────────────────
@router.post("/campaigns/broadcast", response_model=CampaignStatus, summary="Send broadcast message")
def send_broadcast(payload: BroadcastIn):
    """
    Send the same message to multiple recipients.
    This is a basic broadcast - for production use, consider:
    - Rate limiting (WhatsApp allows ~80 messages/second)
    - Message templates for non-active conversations
    - Database storage for campaign tracking
    """
    campaign_id = f"camp_{int(datetime.now().timestamp())}"
    results = []
    sent = 0
    failed = 0
    
    for recipient in payload.recipients:
        try:
            msg_id = wa_client.send_text(to=recipient, text=payload.message)
            results.append({
                "recipient": recipient,
                "status": "sent",
                "message_id": msg_id
            })
            sent += 1
        except Exception as e:
            log.error(f"Failed to send to {recipient}: {e}")
            results.append({
                "recipient": recipient,
                "status": "failed",
                "error": str(e)
            })
            failed += 1
    
    campaign_status = {
        "campaign_id": campaign_id,
        "campaign_name": payload.campaign_name,
        "total_recipients": len(payload.recipients),
        "sent": sent,
        "failed": failed,
        "timestamp": datetime.now().isoformat(),
        "results": results
    }
    
    # Store campaign
    campaigns_buffer.appendleft(campaign_status)
    
    return campaign_status

@router.get("/campaigns", summary="List recent campaigns")
def list_campaigns(limit: int = 50):
    """Get recent broadcast campaigns"""
    return list(campaigns_buffer)[:limit]

@router.get("/campaigns/{campaign_id}", summary="Get campaign details")
def get_campaign(campaign_id: str):
    """Get specific campaign details"""
    for campaign in campaigns_buffer:
        if campaign["campaign_id"] == campaign_id:
            return campaign
    raise HTTPException(status_code=404, detail="Campaign not found")