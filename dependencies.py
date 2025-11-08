# dependencies.py
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import RedirectResponse

# Import JWT auth functions
from jwt_auth import JWTAuth

# Security scheme
security = HTTPBearer(auto_error=False)  # auto_error=False allows it to be optional


def get_current_user(request: Request) -> Optional[str]:
    """Get current authenticated user from session"""
    return request.session.get("username")


def require_auth(request: Request):
    """Dependency to require authentication (session-based for HTML UI)"""
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


async def get_current_user_flexible(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict[str, Any]:
    """
    Flexible authentication - accepts BOTH session and JWT
    
    For HTML UI: Uses session authentication
    For React/API: Uses JWT Bearer token
    
    Returns user info dict
    """
    # Try JWT authentication first (for React frontend)
    if credentials and credentials.credentials:
        try:
            # Decode JWT token
            payload = JWTAuth.decode_token(credentials.credentials)
            
            # Return user info from JWT
            return {
                "auth_type": "jwt",
                "user_id": JWTAuth.get_user_id(payload),
                "tenant_id": JWTAuth.get_tenant_id(payload),
                "username": payload.get("email") or payload.get("username"),
                "payload": payload
            }
        except HTTPException:
            # JWT validation failed, fall through to session auth
            pass
    
    # Try session authentication (for HTML UI)
    username = request.session.get("username")
    if username:
        return {
            "auth_type": "session",
            "username": username,
            "tenant_id": "default",  # Default tenant for session users
            "user_id": username
        }
    
    # No authentication found
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide JWT token or login via session."
    )


async def get_tenant_id_flexible(
    user: Dict[str, Any] = Depends(get_current_user_flexible)
) -> str:
    """
    Get tenant_id from either JWT or session
    
    - JWT users: Get from token payload
    - Session users: Use default tenant
    """
    tenant_id = user.get("tenant_id")
    
    if not tenant_id:
        # Fallback to default for session users
        tenant_id = "default"
    
    return tenant_id


async def require_auth_flexible(
    user: Dict[str, Any] = Depends(get_current_user_flexible)
) -> Dict[str, Any]:
    """
    Require authentication (either session or JWT)
    Use this for API endpoints that should work with both HTML UI and React
    """
    return user