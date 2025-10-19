# routers/groups.py
import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database import get_db, Group

log = logging.getLogger("whatspy.groups")

router = APIRouter()

# ────────────────────────────────
# Models
# ────────────────────────────────

class GroupCreate(BaseModel):
    group_id: str
    name: str
    description: Optional[str] = None
    participants: List[str] = []
    admins: List[str] = []


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


# ────────────────────────────────
# Endpoints
# ────────────────────────────────

@router.get("/groups", summary="List all groups")
def list_groups(
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """Get all groups"""
    try:
        query = db.query(Group)
        
        if active_only:
            query = query.filter(Group.is_active == True)
        
        groups = query.order_by(desc(Group.updated_at)).all()
        return [g.to_dict() for g in groups]
    except Exception as e:
        log.exception("list_groups failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/groups/{group_id}", summary="Get group details")
def get_group(group_id: str, db: Session = Depends(get_db)):
    """Get specific group"""
    try:
        group = db.query(Group).filter(Group.group_id == group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        return group.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        log.exception("get_group failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/groups", summary="Create group")
def create_group(payload: GroupCreate, db: Session = Depends(get_db)):
    """Create a new group record"""
    try:
        existing = db.query(Group).filter(Group.group_id == payload.group_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Group already exists")
        
        group = Group(
            group_id=payload.group_id,
            name=payload.name,
            description=payload.description,
            participants=payload.participants,
            admins=payload.admins
        )
        db.add(group)
        db.commit()
        db.refresh(group)
        
        return {"ok": True, "group": group.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("create_group failed")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/groups/{group_id}", summary="Update group")
def update_group(group_id: str, payload: GroupUpdate, db: Session = Depends(get_db)):
    """Update group information"""
    try:
        group = db.query(Group).filter(Group.group_id == group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        
        if payload.name is not None:
            group.name = payload.name
        if payload.description is not None:
            group.description = payload.description
        if payload.is_active is not None:
            group.is_active = payload.is_active
        
        db.commit()
        db.refresh(group)
        
        return {"ok": True, "group": group.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("update_group failed")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/groups/{group_id}", summary="Delete group")
def delete_group(group_id: str, db: Session = Depends(get_db)):
    """Delete a group"""
    try:
        group = db.query(Group).filter(Group.group_id == group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        
        db.delete(group)
        db.commit()
        
        return {"ok": True, "message": "Group deleted"}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("delete_group failed")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))