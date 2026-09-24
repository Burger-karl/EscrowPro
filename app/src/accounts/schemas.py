
import uuid

from pydantic import BaseModel, EmailStr, Field

from app.src.accounts.models import UserRole


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    role: UserRole


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool

    model_config = {"from_attributes": True}


class FreelancerOut(BaseModel):
    
    id: uuid.UUID
    full_name: str
    email: EmailStr

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class RefreshIn(BaseModel):
    refresh_token: str