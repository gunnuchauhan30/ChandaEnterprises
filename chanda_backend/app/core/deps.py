from typing import Iterable
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise credentials_exception
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled")
    return user


def require_roles(*allowed_roles: Iterable[str]):
    """
    Usage: Depends(require_roles("admin", "store_manager"))
    Module access map (per spec):
      admin           -> everything
      store_manager   -> inventory, purchase GRN receive, issue approval, returns
      purchase        -> supplier master, purchase/GRN, high-stock confirmation
      production      -> employee requests, route card / job card issue view
      management       -> dashboard, reports (read-only across modules)
    """
    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role.value == "admin":
            return current_user  # admin bypasses all module restrictions
        if current_user.role.value not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role.value}' is not permitted to access this module",
            )
        return current_user
    return checker
