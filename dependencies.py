# dependencies.py
from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse


def get_current_user(request: Request) -> Optional[str]:
    """Get current authenticated user from session"""
    return request.session.get("username")


def require_auth(request: Request):
    """Dependency to require authentication"""
    username = get_current_user(request)
    if not username:
        # For API endpoints, return 401
        if request.url.path.startswith("/api/"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated"
            )
        # For page routes, redirect to login
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Not authenticated",
            headers={"Location": "/login"}
        )
    return username


def optional_auth(request: Request) -> Optional[str]:
    """Optional authentication - returns username if logged in, None otherwise"""
    return get_current_user(request)