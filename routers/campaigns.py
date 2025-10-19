# routers/templates.py
import logging
from typing import List, Optional, Dict
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database import get_db, MessageTemplate

log = logging.getLogger("whatspy.templates")

router = APIRouter()
wa_client = None


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
def create_template(payload: TemplateCreate, db: Session = Depends(get_db)):
    """
    Create a reusable message template.
    Variables in content should be wrapped like: {{variable_name}}
    """
    try:
        # Check if template already exists
        existing = db.query(MessageTemplate).filter(MessageTemplate.name == payload.name).first()
        if existing:
            raise HTTPException(status_code=400, detail="Template already exists")
        
        template = MessageTemplate(
            name=payload.name,
            content=payload.content,
            variables=payload.variables,
            category=payload.category
        )
        db.add(template)
        db.commit()
        db.refresh(template)
        
        return {"ok": True, "template": template.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("create_template failed")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates", summary="List all templates")
def list_templates(category: Optional[str] = None, db: Session = Depends(get_db)):
    """Get all templates, optionally filtered by category"""
    try:
        query = db.query(MessageTemplate)
        
        if category:
            query = query.filter(MessageTemplate.category == category)
        
        templates = query.order_by(desc(MessageTemplate.created_at)).all()
        return [t.to_dict() for t in templates]
    except Exception as e:
        log.exception("list_templates failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates/{name}", summary="Get template by name")
def get_template(name: str, db: Session = Depends(get_db)):
    """Get specific template"""
    try:
        template = db.query(MessageTemplate).filter(MessageTemplate.name == name).first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        return template.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        log.exception("get_template failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/templates/{name}", summary="Update template")
def update_template(name: str, payload: TemplateUpdate, db: Session = Depends(get_db)):
    """Update existing template"""
    try:
        template = db.query(MessageTemplate).filter(MessageTemplate.name == name).first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        if payload.content is not None:
            template.content = payload.content
        if payload.variables is not None:
            template.variables = payload.variables
        if payload.category is not None:
            template.category = payload.category
        
        template.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(template)
        
        return {"ok": True, "template": template.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("update_template failed")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/templates/{name}", summary="Delete template")
def delete_template(name: str, db: Session = Depends(get_db)):
    """Delete a template"""
    try:
        template = db.query(MessageTemplate).filter(MessageTemplate.name == name).first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        db.delete(template)
        db.commit()
        
        return {"ok": True, "message": "Template deleted"}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("delete_template failed")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/templates/send", summary="Send message using template")
def send_with_template(payload: TemplateSend, db: Session = Depends(get_db)):
    """
    Send a message using a saved template.
    Variables in the template will be replaced with provided values.
    """
    try:
        template = db.query(MessageTemplate).filter(MessageTemplate.name == payload.template_name).first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        content = template.content
        
        # Replace variables
        for var_name, var_value in payload.variables.items():
            placeholder = "{{" + var_name + "}}"
            content = content.replace(placeholder, var_value)
        
        # Check for unreplaced variables
        if "{{" in content and "}}" in content:
            raise HTTPException(
                status_code=400,
                detail="Not all variables were provided. Template requires: " + str(template.variables)
            )
        
        # Send message
        msg_id = wa_client.send_text(to=payload.to, text=content)
        
        # Update usage count
        template.usage_count += 1
        db.commit()
        
        return {
            "ok": True,
            "message_id": msg_id,
            "template_used": payload.template_name,
            "final_content": content
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception("send_with_template failed")
        raise HTTPException(status_code=500, detail=str(e))