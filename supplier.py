from typing import Optional
import re

from pydantic import EmailStr, field_validator
from sqlmodel import SQLModel, Field


class Supplier(SQLModel, table=True):

    id: Optional[int] = Field(
        default=None,
        primary_key=True
    )

    name: str = Field(
        unique=True,
        index=True,
        min_length=2,
        max_length=100
    )

    contact_person: str = Field(
        min_length=2,
        max_length=100
    )

    email: str = Field(
        unique=True,
        index=True
    )

    phone: str

    is_active: bool = True


class SupplierCreate(SQLModel):

    name: str = Field(
        min_length=2,
        max_length=100
    )

    contact_person: str = Field(
        min_length=2,
        max_length=100
    )

    email: EmailStr

    phone: str

    is_active: bool = True


    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str):

        v = v.strip()

        pattern = (
            r"^(07|01)\d{8}$"
            r"|^\+254(7|1)\d{8}$"
        )

        if not v:
            raise ValueError(
                "Phone number cannot be empty"
            )

        if not re.fullmatch(
            pattern,
            v
        ):
            raise ValueError(
                "Invalid Kenyan phone number format"
            )

        return v