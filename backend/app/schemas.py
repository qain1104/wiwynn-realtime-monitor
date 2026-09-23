from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field

Role = Literal['admin', 'user', 'viewer']
class Register(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
class Login(Register):
    pass
class UserOut(BaseModel):
    id: int
    email: str
    role: Role
    model_config = ConfigDict(from_attributes=True)
class RoleChange(BaseModel):
    role: Role
class RecordIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    value: float = Field(allow_inf_nan=False)
    category: str = Field(min_length=1, max_length=100)
    timestamp: datetime | None = None
class RecordUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    value: float | None = Field(default=None, allow_inf_nan=False)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    timestamp: datetime | None = None
class RecordOut(BaseModel):
    id: int
    title: str
    value: float
    category: str
    timestamp: datetime
    creator_id: int | None
    model_config = ConfigDict(from_attributes=True)
