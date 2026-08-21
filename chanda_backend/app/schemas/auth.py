from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class SignupIn(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=6, max_length=100)
    full_name: Optional[str] = None
    role: str = Field(default="production", description="admin|store_manager|purchase|production|management")
    department: Optional[str] = None


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: "UserOut"


class RefreshIn(BaseModel):
    refresh_token: str


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str = Field(min_length=6, max_length=100)


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str]
    role: str
    department: Optional[str]
    is_active: bool
    last_login: Optional[datetime]

    class Config:
        from_attributes = True


class UserRoleUpdate(BaseModel):
    role: Optional[str] = Field(default=None, description="admin|store_manager|purchase|production|management")
    is_active: Optional[bool] = None


TokenOut.model_rebuild()
