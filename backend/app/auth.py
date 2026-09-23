from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.ext.asyncio import AsyncSession
from .db import get_db
from .models import User
from .settings import settings

hashing = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)
def token_for(user: User) -> str:
    return jwt.encode({'sub': str(user.id), 'exp': datetime.now(timezone.utc) + timedelta(hours=8)}, settings.jwt_secret, algorithm='HS256')
async def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: AsyncSession = Depends(get_db)) -> User:
    try:
        if credentials is None:
            raise ValueError('Missing credentials')
        data = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=['HS256'])
        user = await db.get(User, int(data['sub']))
    except (jwt.PyJWTError, KeyError, ValueError):
        user = None
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid or missing token',
            headers={'WWW-Authenticate': 'Bearer'},
        )
    return user
def require(*roles: str):
    async def check(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail='Insufficient permissions')
        return user
    return check
