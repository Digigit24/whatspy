# routers/contacts.py
import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database import get_db, Contact

log = logging.getLogger("whatspy.contacts")

router = APIRouter()

# ────────────────────────────────
# Models
# ────────────────────────────────

class ContactCreate(BaseModel):
    phone: str = Field(..., description="Phone number")
    name: Optional[str] = None
    notes: Optional[str] = None
    labels: Optional[List[str]] = []
    groups: Optional[List[str]] = []


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    notes: Optional[str] = None
    labels: Optional[List[str]] = None
    groups: Optional[List[str]] = None
    is_business: Optional[bool] = None


# ────────────────────────────────
# Endpoints
# ────────────────────────────────

@router.get("/contacts", summary="List all contacts")
def list_contacts(
    search: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get all contacts with optional search"""
    try:
        query = db.query(Contact)
        
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                (Contact.name.ilike(search_pattern)) | 
                (Contact.phone.ilike(search_pattern))
            )
        
        contacts = query.order_by(desc(Contact.last_seen)).limit(limit).all()
        return [c.to_dict() for c in contacts]
    except Exception as e:
        log.exception("list_contacts failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contacts/{phone}", summary="Get contact by phone")
def get_contact(phone: str, db: Session = Depends(get_db)):
    """Get specific contact details"""
    try:
        contact = db.query(Contact).filter(Contact.phone == phone).first()
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")
        return contact.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        log.exception("get_contact failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/contacts", summary="Create contact")
def create_contact(payload: ContactCreate, db: Session = Depends(get_db)):
    """Create a new contact"""
    try:
        existing = db.query(Contact).filter(Contact.phone == payload.phone).first()
        if existing:
            raise HTTPException(status_code=400, detail="Contact already exists")
        
        contact = Contact(
            phone=payload.phone,
            name=payload.name,
            notes=payload.notes,
            labels=payload.labels
        )
        db.add(contact)
        db.commit()
        db.refresh(contact)
        
        return {"ok": True, "contact": contact.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("create_contact failed")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/contacts/{phone}", summary="Update contact")
def update_contact(phone: str, payload: ContactUpdate, db: Session = Depends(get_db)):
    """Update contact information"""
    try:
        contact = db.query(Contact).filter(Contact.phone == phone).first()
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")
        
        if payload.name is not None:
            contact.name = payload.name
        if payload.notes is not None:
            contact.notes = payload.notes
        if payload.labels is not None:
            contact.labels = payload.labels
        if payload.is_business is not None:
            contact.is_business = payload.is_business
        
        contact.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(contact)
        
        return {"ok": True, "contact": contact.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("update_contact failed")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/contacts/{phone}", summary="Delete contact")
def delete_contact(phone: str, db: Session = Depends(get_db)):
    """Delete a contact"""
    try:
        contact = db.query(Contact).filter(Contact.phone == phone).first()
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")
        
        db.delete(contact)
        db.commit()
        
        return {"ok": True, "message": "Contact deleted"}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("delete_contact failed")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))