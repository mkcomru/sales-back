from __future__ import annotations

from enum import Enum

from tortoise import fields

from src.backend.modules.core.base_model import BaseModel


class UserRole(str, Enum):
    """Role of user within a company."""

    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    VIEWER = "viewer"


class User(BaseModel):
    id = fields.IntField(primary_key=True)
    first_name = fields.CharField(max_length=255)
    last_name = fields.CharField(max_length=255)
    email = fields.CharField(max_length=255, unique=True, index=True)
    hashed_password = fields.CharField(max_length=255)
    is_active = fields.BooleanField(default=True)
    is_superuser = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    company_users: fields.ReverseRelation
    refresh_tokens: fields.ReverseRelation

    class Meta:
        table = "users"
        schema = "backend"


class CompanyUser(BaseModel):
    id = fields.IntField(primary_key=True)
    user: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.User", related_name="company_users", on_delete=fields.CASCADE
    )
    company: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.Company", related_name="company_users", on_delete=fields.CASCADE
    )
    role = fields.CharEnumField(UserRole, max_length=20, default=UserRole.VIEWER)
    created_at = fields.DatetimeField(auto_now_add=True)
    work_schedule = fields.JSONField(null=True)
    is_available = fields.BooleanField(default=True)
    last_assigned_at = fields.DatetimeField(null=True)

    def get_full_name(self) -> str:
        """Get full name of the user.

        Returns:
            Full name as "first_name last_name" with stripped whitespace
        """
        return f"{self.user.first_name} {self.user.last_name}".strip()

    class Meta:
        table = "company_users"
        schema = "backend"
        unique_together = (("user", "company"),)
