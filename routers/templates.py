# routers/templates.py
import logging
from typing import List, Optional, Dict, Any
from collections import deque

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import MAX_BUFFER

log = logging.getLogger("whatspy.templates")

router = APIRouter()
wa_client = None

# Template storage (in-memory for now)
templates_store: Dict[str, Dict[str, Any]] = {}

def init_wa_client(client):
    """Initialize WhatsApp client"""
    global wa_client
    wa_client = client

# ────────────────────────────────
# Models
# ────────────────────────────────
class TemplateCreate(BaseModel):
    """Create a message template"""
    name: str = Field(..., description="Unique template name")
    content: str = Field(..., min_length=1, max_length=4096)
    variables: Optional[List[str]] = Field(default=[], description="Variables like {{name}}, {{code}}")
    category: Optional[str] = Field("general", description="Template category")

class TemplateUpdate(BaseModel):
    """Update template"""
    content: Optional[str] = None
    variables: Optional[List[str]] = None
    category: Optional[str] = None

class TemplateSend(BaseModel):
    """Send message using template"""
    to: str = Field(..., description="Recipient phone number")
    template_name: str = Field(..., description="Template name to use")
    variables: Optional[Dict[str, str]] = Field(default={}, description="Variable values")

# ────────────────────────────────
# Endpoints
# ────────────────────────────────
@router.post("/templates", summary="Create message template")
def create_template(payload: TemplateCreate):
    """
    Create a reusable message template.
    Variables in content should be wrapped like: {{variable_name}}
    
    Example:
    - content: "Hi {{name}}, your code is {{code}}"
    - variables: ["name", "code"]
    """
    if payload.name in templates_store:
        raise HTTPException(status_code=400, detail="Template already exists")
    
    template = {
        "name": payload.name,
        "content": payload.content,
        "variables": payload.variables,
        "category": payload.category,
        "created_at": None,  # TODO: add timestamp
        "usage_count": 0
    }
    
    templates_store[payload.name] = template
    return {"ok": True, "template": template}

@router.get("/templates", summary="List all templates")
def list_templates(category: Optional[str] = None):
    """Get all templates, optionally filtered by category"""
    templates = list(templates_store.values())
    
    if category:
        templates = [t for t in templates if t.get("category") == category]
    
    return templates

@router.get("/templates/{name}", summary="Get template by name")
def get_template(name: str):
    """Get specific template"""
    if name not in templates_store:
        raise HTTPException(status_code=404, detail="Template not found")
    return templates_store[name]

@router.put("/templates/{name}", summary="Update template")
def update_template(name: str, payload: TemplateUpdate):
    """Update existing template"""
    if name not in templates_store:
        raise HTTPException(status_code=404, detail="Template not found")
    
    template = templates_store[name]
    
    if payload.content is not None:
        template["content"] = payload.content
    if payload.variables is not None:
        template["variables"] = payload.variables
    if payload.category is not None:
        template["category"] = payload.category
    
    return {"ok": True, "template": template}

@router.delete("/templates/{name}", summary="Delete template")
def delete_template(name: str):
    """Delete a template"""
    if name not in templates_store:
        raise HTTPException(status_code=404, detail="Template not found")
    
    del templates_store[name]
    return {"ok": True, "message": "Template deleted"}

@router.post("/templates/send", summary="Send message using template")
def send_with_template(payload: TemplateSend):
    """
    Send a message using a saved template.
    Variables in the template will be replaced with provided values.
    """
    if payload.template_name not in templates_store:
        raise HTTPException(status_code=404, detail="Template not found")
    
    template = templates_store[payload.template_name]
    content = template["content"]
    
    # Replace variables
    for var_name, var_value in payload.variables.items():
        placeholder = "{{" + var_name + "}}"
        content = content.replace(placeholder, var_value)
    
    # Check for unreplaced variables
    if "{{" in content and "}}" in content:
        raise HTTPException(
            status_code=400,
            detail="Not all variables were provided. Template requires: " + str(template["variables"])
        )
    
    try:
        msg_id = wa_client.send_text(to=payload.to, text=content)
        
        # Update usage count
        template["usage_count"] = template.get("usage_count", 0) + 1
        
        return {
            "ok": True,
            "message_id": msg_id,
            "template_used": payload.template_name,
            "final_content": content
        }
    except Exception as e:
        log.exception("Template send failed")
        raise HTTPException(status_code=500, detail=str(e))