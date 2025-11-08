# jwt_auth.py
"""
JWT Authentication middleware for multi-tenant WhatsApp application
Validates JWT tokens from Django CRM app
"""
import os
import jwt
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from database import get_db
from config import JWT_SECRET_KEY, JWT_ALGORITHM

# Security scheme for Swagger UI
security = HTTPBearer()


class JWTAuth:
    """JWT Authentication handler"""
    
    @staticmethod
    def decode_token(token: str) -> Dict[str, Any]:
        """
        Decode and validate JWT token from Django CRM app
        
        Args:
            token: JWT token string
            
        Returns:
            Decoded token payload
            
        Raises:
            HTTPException: If token is invalid or expired
        """
        try:
            # Decode JWT token using secret from environment
            payload = jwt.decode(
                token,
                JWT_SECRET_KEY,
                algorithms=[JWT_ALGORITHM]
            )
            
            # Check if token has expired
            exp = payload.get('exp')
            if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
                raise HTTPException(
                    status_code=401,
                    detail="Token has expired"
                )
            
            return payload
            
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=401,
                detail="Token has expired"
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=401,
                detail="Invalid token"
            )
        except Exception as e:
            raise HTTPException(
                status_code=401,
                detail=f"Token validation failed: {str(e)}"
            )
    
    @staticmethod
    def get_tenant_id(payload: Dict[str, Any]) -> Optional[str]:
        """
        Extract tenant_id from JWT payload
        
        Args:
            payload: Decoded JWT payload
            
        Returns:
            Tenant ID or None
        """
        # Try different possible keys for tenant ID
        tenant_id = (
            payload.get('tenant_id') or 
            payload.get('tenant') or 
            payload.get('tenantId')
        )
        
        if isinstance(tenant_id, dict):
            # If tenant is an object, get its ID
            tenant_id = tenant_id.get('id') or tenant_id.get('tenant_id')
        
        return str(tenant_id) if tenant_id else None
    
    @staticmethod
    def get_user_id(payload: Dict[str, Any]) -> Optional[str]:
        """
        Extract user_id from JWT payload
        
        Args:
            payload: Decoded JWT payload
            
        Returns:
            User ID or None
        """
        user_id = (
            payload.get('user_id') or 
            payload.get('sub') or 
            payload.get('id')
        )
        return str(user_id) if user_id else None
    
    @staticmethod
    def has_module_access(payload: Dict[str, Any], module: str) -> bool:
        """
        Check if user has access to a specific module
        
        Args:
            payload: Decoded JWT payload
            module: Module name (e.g., 'crm', 'whatsapp')
            
        Returns:
            True if user has access, False otherwise
        """
        # Check in modules array
        modules = payload.get('modules', [])
        if module in modules:
            return True
        
        # Check in enabled_modules
        enabled_modules = payload.get('enabled_modules', [])
        if module in enabled_modules:
            return True
        
        # Check in permissions
        permissions = payload.get('permissions', [])
        if f'{module}.access' in permissions:
            return True
        
        return False


# Dependency functions for FastAPI

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> Dict[str, Any]:
    """
    FastAPI dependency to get current authenticated user from JWT
    
    Args:
        credentials: HTTP Bearer credentials
        
    Returns:
        Decoded JWT payload with user info
        
    Raises:
        HTTPException: If authentication fails
    """
    token = credentials.credentials
    payload = JWTAuth.decode_token(token)
    return payload


async def get_current_tenant_id(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> str:
    """
    FastAPI dependency to get current tenant ID
    
    Args:
        current_user: Current user from JWT
        
    Returns:
        Tenant ID
        
    Raises:
        HTTPException: If tenant ID not found
    """
    tenant_id = JWTAuth.get_tenant_id(current_user)
    
    if not tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Tenant ID not found in token"
        )
    
    return tenant_id


async def require_module_access(
    module: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    FastAPI dependency to require access to a specific module
    
    Args:
        module: Module name to check
        current_user: Current user from JWT
        
    Returns:
        Current user if access granted
        
    Raises:
        HTTPException: If user doesn't have access
    """
    if not JWTAuth.has_module_access(current_user, module):
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: {module} module not enabled"
        )
    
    return current_user


# Convenience function for WhatsApp module access
async def require_whatsapp_access(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """FastAPI dependency to require WhatsApp module access"""
    return await require_module_access('whatsapp', current_user)