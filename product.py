from datetime import datetime
from decimal import Decimal
from typing import Optional
import re

from pydantic import field_validator, model_validator
from sqlmodel import SQLModel, Field


ALLOWED_BRANDS = [
    "HP",
    "Dell",
    "Lenovo",
    "Apple",
    "Samsung",
    "Intel",
    "AMD",
    "Corsair",
    "Logitech",
    "Other",
]


ALLOWED_CATEGORIES = [
    "Laptops",
    "Monitors",
    "Storage",
    "Processors",
    "Memory",
    "Keyboards",
    "Mice",
    "Accessories",
]


CATEGORY_ABBREVIATIONS = {
    "LAP": "Laptops",
    "MON": "Monitors",
    "STO": "Storage",
    "PRO": "Processors",
    "MEM": "Memory",
    "KEY": "Keyboards",
    "MOU": "Mice",
    "ACC": "Accessories",
}


class Product(SQLModel, table=True):
    id: Optional[int] = Field(
        default=None,
        primary_key=True
    )

    name: str = Field(
        index=True,
        min_length=2,
        max_length=100
    )

    description: str = Field(
        min_length=10,
        max_length=500
    )

    brand: str = Field(index=True)

    category: str = Field(index=True)

    price: float = Field(
        gt=0
    )

    stock: int = Field(
        ge=0,
        le=5000
    )

    warranty_months: int = Field(
        ge=0,
        le=36
    )

    sku: str = Field(
        unique=True,
        index=True
    )

    supplier_id: Optional[int] = Field(
        default=None,
        foreign_key="supplier.id"
    )

    created_at: datetime = Field(
        default_factory=datetime.utcnow
    )

    updated_at: datetime = Field(
        default_factory=datetime.utcnow
    )


class ProductCreate(SQLModel):

    name: str = Field(
        min_length=2,
        max_length=100
    )

    description: str = Field(
        min_length=10,
        max_length=500
    )

    brand: str

    category: str

    price: float

    stock: int = Field(
        ge=0,
        le=5000
    )

    warranty_months: int

    sku: str

    supplier_id: Optional[int] = None


    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str):

        v = v.strip()

        if not v:
            raise ValueError(
                "Product name cannot be empty"
            )

        if not v[0].isupper():
            raise ValueError(
                "Product name must start with a capital letter"
            )

        if re.search(
            r"[^a-zA-Z0-9\s-]",
            v
        ):
            raise ValueError(
                "Product name cannot contain special characters "
                "except spaces and hyphens"
            )

        if not re.search(
            r"[A-Za-z]",
            v
        ):
            raise ValueError(
                "Product name must contain at least one word"
            )

        return v


    @field_validator("brand")
    @classmethod
    def validate_brand(cls, v: str):

        v = v.strip()

        brand_lookup = {
            brand.lower(): brand
            for brand in ALLOWED_BRANDS
        }

        normalized = brand_lookup.get(
            v.lower()
        )

        if normalized is None:
            raise ValueError(
                f"Brand must be one of: "
                f"{', '.join(ALLOWED_BRANDS)}"
            )

        return normalized


    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str):

        v = v.strip()

        category_lookup = {
            category.lower(): category
            for category in ALLOWED_CATEGORIES
        }

        normalized = category_lookup.get(
            v.lower()
        )

        if normalized is None:
            raise ValueError(
                f"Category must be one of: "
                f"{', '.join(ALLOWED_CATEGORIES)}"
            )

        return normalized


    @field_validator("price")
    @classmethod
    def validate_price(cls, v: float):

        if v < 100:
            raise ValueError(
                "Product price cannot be below KSh 100"
            )

        if v > 500000:
            raise ValueError(
                "Product price cannot exceed KSh 500,000"
            )

        decimal_value = Decimal(
            str(v)
        )

        if decimal_value.as_tuple().exponent < -2:
            raise ValueError(
                "Product price cannot have more than "
                "2 decimal places"
            )

        return round(
            v,
            2
        )


    @field_validator("sku")
    @classmethod
    def validate_sku(cls, v: str):

        v = v.strip().upper()

        pattern = (
            r"^([A-Z]{3,4})-"
            r"([A-Z]{2,4})-"
            r"([0-9]{4})$"
        )

        match = re.fullmatch(
            pattern,
            v
        )

        if not match:
            raise ValueError(
                "SKU must follow the format "
                "CAT-BRAND-XXXX, "
                "for example LAP-DEL-0001"
            )

        category_code = match.group(1)

        if category_code not in CATEGORY_ABBREVIATIONS:
            raise ValueError(
                "Invalid category abbreviation. "
                "Allowed values: "
                f"{', '.join(CATEGORY_ABBREVIATIONS.keys())}"
            )

        return v


    @model_validator(mode="after")
    def validate_business_rules(self):

        if self.warranty_months < 0:
            raise ValueError(
                "Warranty cannot be negative"
            )

        if self.warranty_months > 36:
            raise ValueError(
                "Warranty cannot exceed 36 months"
            )

        if (
            self.price > 50000
            and self.warranty_months < 12
        ):
            raise ValueError(
                "Products costing more than "
                "KSh 50,000 must have at least "
                "12 months warranty"
            )

        return self


class StockAdjustment(SQLModel):

    product_id: int

    quantity_to_add: int = Field(
        gt=0,
        le=5000
    )