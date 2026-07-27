from datetime import datetime
from typing import List

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Request,
    status,
)

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from sqlalchemy.exc import IntegrityError

from sqlmodel import Session, select

import logging

from database import create_db_and_tables, get_session

from models.product import (
    Product,
    ProductCreate,
    StockAdjustment,
    ALLOWED_CATEGORIES,
)

from models.supplier import (
    Supplier,
    SupplierCreate,
)


# ============================================================
# APPLICATION SETUP
# ============================================================

app = FastAPI(
    title="TechVault Inventory API",
    description=(
        "A robust inventory management API for TechVault, "
        "a Nairobi-based electronics retailer."
    ),
    version="1.0.0",
)


# ============================================================
# LOGGING CONFIGURATION
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s - "
        "%(name)s - "
        "%(levelname)s - "
        "%(message)s"
    ),
)

logger = logging.getLogger(__name__)


# ============================================================
# DATABASE STARTUP
# ============================================================

@app.on_event("startup")
def on_startup():
    """
    Create database tables when the application starts.
    """
    create_db_and_tables()

    logger.info(
        "TechVault Inventory API started successfully"
    )


# ============================================================
# STANDARD ERROR RESPONSE HELPER
# ============================================================

def create_error_response(
    status_code: int,
    message: str,
    path: str,
    errors: list | None = None,
):
    """
    Create a consistent error response for all exceptions.
    """

    response = {
        "success": False,
        "status_code": status_code,
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
        "path": path,
    }

    if errors is not None:
        response["errors"] = errors

    return response


# ============================================================
# GLOBAL EXCEPTION HANDLER
# HTTPException
# ============================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(
    request: Request,
    exc: HTTPException,
):
    """
    Handle HTTPException errors consistently.
    """

    logger.warning(
        "HTTP Exception: "
        f"{request.method} "
        f"{request.url.path} "
        f"- Status: {exc.status_code} "
        f"- Detail: {exc.detail}"
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=create_error_response(
            status_code=exc.status_code,
            message=str(exc.detail),
            path=request.url.path,
        ),
    )


# ============================================================
# GLOBAL EXCEPTION HANDLER
# REQUEST VALIDATION ERROR
# ============================================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    """
    Handle Pydantic/FastAPI validation errors.

    Returns a user-friendly list of validation errors.
    """

    errors = []

    for error in exc.errors():

        # Convert location tuple into readable string.
        #
        # Example:
        # ("body", "name")
        #
        # becomes:
        # "body.name"

        field_location = ".".join(
            str(location)
            for location in error["loc"]
        )

        errors.append(
            {
                "field": field_location,
                "message": error["msg"],
                "type": error["type"],
            }
        )

    logger.warning(
        "Validation error: "
        f"{request.method} "
        f"{request.url.path} "
        f"- Errors: {errors}"
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=create_error_response(
            status_code=422,
            message="Validation error",
            path=request.url.path,
            errors=errors,
        ),
    )


# ============================================================
# GLOBAL EXCEPTION HANDLER
# INTEGRITY ERROR
# ============================================================

@app.exception_handler(IntegrityError)
async def integrity_error_handler(
    request: Request,
    exc: IntegrityError,
):
    """
    Handle database integrity errors.

    Examples:
    - Duplicate SKU
    - Duplicate supplier email
    - Duplicate supplier name
    - Foreign key violations
    """

    logger.error(
        "Database integrity error: "
        f"{request.method} "
        f"{request.url.path} "
        f"- {exc}"
    )

    # Convert database error to lowercase
    # so we can search for common constraint names.

    error_text = str(exc.orig).lower()

    # Default error message

    error_message = (
        "Database constraint violation"
    )

    # Duplicate SKU

    if "sku" in error_text:

        error_message = (
            "A product with this SKU already exists"
        )

    # Duplicate supplier email

    elif "email" in error_text:

        error_message = (
            "A supplier with this email already exists"
        )

    # Duplicate supplier name

    elif "name" in error_text:

        error_message = (
            "A supplier with this name already exists"
        )

    # Foreign key error

    elif (
        "foreign key" in error_text
        or "foreign key constraint" in error_text
    ):

        error_message = (
            "The referenced supplier does not exist"
        )

    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=create_error_response(
            status_code=409,
            message=error_message,
            path=request.url.path,
        ),
    )


# ============================================================
# GLOBAL EXCEPTION HANDLER
# GENERAL UNHANDLED EXCEPTIONS
# ============================================================

@app.exception_handler(Exception)
async def general_exception_handler(
    request: Request,
    exc: Exception,
):
    """
    Handle unexpected server errors.

    The real exception is logged internally,
    while the client receives a safe generic message.
    """

    logger.exception(
        "Unhandled exception: "
        f"{request.method} "
        f"{request.url.path} "
        f"- {exc}"
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=create_error_response(
            status_code=500,
            message=(
                "An internal server error occurred"
            ),
            path=request.url.path,
        ),
    )


# ============================================================
# PRODUCT ENDPOINTS
# ============================================================


# ------------------------------------------------------------
# CREATE PRODUCT
# ------------------------------------------------------------

@app.post(
    "/products",
    response_model=Product,
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    product_data: ProductCreate,
    session: Session = Depends(get_session),
):
    """
    Create a new product.

    Validates:
    - Product name
    - Description
    - Brand
    - Category
    - Price
    - Stock
    - Warranty
    - SKU
    - Supplier
    """

    # --------------------------------------------------------
    # Check supplier exists if supplier_id is provided
    # --------------------------------------------------------

    if product_data.supplier_id is not None:

        supplier = session.get(
            Supplier,
            product_data.supplier_id,
        )

        if supplier is None:

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "Supplier with ID "
                    f"{product_data.supplier_id} "
                    "does not exist"
                ),
            )

        # Optional business rule:
        # Do not allow products to be assigned
        # to inactive suppliers.

        if not supplier.is_active:

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Cannot assign a product to "
                    "an inactive supplier"
                ),
            )

    # --------------------------------------------------------
    # Create Product object
    # --------------------------------------------------------

    product = Product(
        **product_data.model_dump()
    )

    # --------------------------------------------------------
    # Save Product
    # --------------------------------------------------------

    session.add(product)

    session.commit()

    session.refresh(product)

    logger.info(
        "Product created successfully: "
        f"ID={product.id}, "
        f"Name={product.name}, "
        f"SKU={product.sku}"
    )

    return product


# ------------------------------------------------------------
# GET ALL PRODUCTS
# ------------------------------------------------------------

@app.get(
    "/products",
    response_model=list[Product],
)
def get_products(
    session: Session = Depends(get_session),
):
    """
    Return all products.
    """

    products = session.exec(
        select(Product)
    ).all()

    return products


# ------------------------------------------------------------
# GET SINGLE PRODUCT
# ------------------------------------------------------------

@app.get(
    "/products/{product_id}",
    response_model=Product,
)
def get_product(
    product_id: int,
    session: Session = Depends(get_session),
):
    """
    Return one product by ID.
    """

    product = session.get(
        Product,
        product_id,
    )

    if product is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    return product


# ------------------------------------------------------------
# DELETE PRODUCT
# ------------------------------------------------------------

@app.delete(
    "/products/{product_id}",
)
def delete_product(
    product_id: int,
    session: Session = Depends(get_session),
):
    """
    Delete a product by ID.
    """

    product = session.get(
        Product,
        product_id,
    )

    if product is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    session.delete(product)

    session.commit()

    logger.info(
        "Product deleted successfully: "
        f"ID={product_id}"
    )

    return {
        "success": True,
        "message": "Product deleted successfully",
        "product_id": product_id,
    }


# ============================================================
# SUPPLIER ENDPOINTS
# ============================================================


# ------------------------------------------------------------
# CREATE SUPPLIER
# ------------------------------------------------------------

@app.post(
    "/suppliers",
    response_model=Supplier,
    status_code=status.HTTP_201_CREATED,
)
def create_supplier(
    supplier_data: SupplierCreate,
    session: Session = Depends(get_session),
):
    """
    Create a new supplier.

    Email and phone are validated by SupplierCreate.
    """

    supplier = Supplier(
        **supplier_data.model_dump()
    )

    session.add(supplier)

    session.commit()

    session.refresh(supplier)

    logger.info(
        "Supplier created successfully: "
        f"ID={supplier.id}, "
        f"Name={supplier.name}"
    )

    return supplier


# ------------------------------------------------------------
# GET ALL SUPPLIERS
# ------------------------------------------------------------

@app.get(
    "/suppliers",
    response_model=list[Supplier],
)
def get_suppliers(
    session: Session = Depends(get_session),
):
    """
    Return all suppliers.
    """

    suppliers = session.exec(
        select(Supplier)
    ).all()

    return suppliers


# ------------------------------------------------------------
# GET SINGLE SUPPLIER
# ------------------------------------------------------------

@app.get(
    "/suppliers/{supplier_id}",
    response_model=Supplier,
)
def get_supplier(
    supplier_id: int,
    session: Session = Depends(get_session),
):
    """
    Return one supplier by ID.
    """

    supplier = session.get(
        Supplier,
        supplier_id,
    )

    if supplier is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found",
        )

    return supplier


# ============================================================
# EXERCISE 3
# BULK PRICE UPDATE
# ============================================================

@app.patch(
    "/products/bulk-update",
)
def bulk_update_price(
    category: str,
    discount_percent: float,
    session: Session = Depends(get_session),
):
    """
    Apply a percentage discount to all products
    in a specific category.

    Business rules:
    - Discount must be between 0 and 100%.
    - Category must be valid.
    - New price cannot be below KSh 100.
    - Products that pass validation are updated.
    - Products that fail validation are rejected.
    - Operation is logged.
    """

    # --------------------------------------------------------
    # 1. Validate discount percentage
    # --------------------------------------------------------

    if (
        discount_percent < 0
        or discount_percent > 100
    ):

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Discount percentage must be "
                "between 0 and 100"
            ),
        )

    # --------------------------------------------------------
    # 2. Normalize category
    # --------------------------------------------------------

    category = category.strip()

    category_lookup = {
        item.lower(): item
        for item in ALLOWED_CATEGORIES
    }

    normalized_category = category_lookup.get(
        category.lower()
    )

    if normalized_category is None:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Invalid category. "
                "Allowed categories are: "
                f"{', '.join(ALLOWED_CATEGORIES)}"
            ),
        )

    # --------------------------------------------------------
    # 3. Find all products in the category
    # --------------------------------------------------------

    products = session.exec(
        select(Product).where(
            Product.category == normalized_category
        )
    ).all()

    if not products:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "No products found in category "
                f"'{normalized_category}'"
            ),
        )

    # --------------------------------------------------------
    # Prepare result lists
    # --------------------------------------------------------

    updated_products = []

    rejected_products = []

    # --------------------------------------------------------
    # 4. Calculate new prices
    # --------------------------------------------------------

    for product in products:

        # IMPORTANT:
        # Capture old_price BEFORE changing product.price.

        old_price = product.price

        # Calculate discounted price

        new_price = round(
            old_price
            * (1 - discount_percent / 100),
            2,
        )

        # ----------------------------------------------------
        # 5. Check minimum price
        # ----------------------------------------------------

        if new_price < 100:

            rejected_products.append(
                {
                    "product_id": product.id,
                    "product_name": product.name,
                    "current_price": old_price,
                    "calculated_price": new_price,
                    "reason": (
                        "Discount would reduce "
                        "the product price below "
                        "the minimum price of KSh 100"
                    ),
                }
            )

            # Do not update this product

            continue

        # ----------------------------------------------------
        # 6. Update valid product
        # ----------------------------------------------------

        product.price = new_price

        product.updated_at = datetime.utcnow()

        updated_products.append(
            {
                "product_id": product.id,
                "product_name": product.name,
                "old_price": old_price,
                "new_price": new_price,
                "discount_percent": discount_percent,
            }
        )

    # --------------------------------------------------------
    # 7. Commit all successful updates
    # --------------------------------------------------------

    session.commit()

    # --------------------------------------------------------
    # 8. Log operation
    # --------------------------------------------------------

    logger.info(
        "Bulk price update completed: "
        f"Category={normalized_category}, "
        f"Discount={discount_percent}%, "
        f"Updated={len(updated_products)}, "
        f"Rejected={len(rejected_products)}"
    )

    # --------------------------------------------------------
    # 9. Return summary
    # --------------------------------------------------------

    return {
        "success": True,
        "message": (
            "Bulk price update completed"
        ),
        "category": normalized_category,
        "discount_percent": discount_percent,
        "updated_count": len(
            updated_products
        ),
        "rejected_count": len(
            rejected_products
        ),
        "updated_products": updated_products,
        "rejected_products": rejected_products,
    }


# ============================================================
# EXERCISE 4
# STOCK ADJUSTMENT
# ============================================================

@app.patch(
    "/products/adjust-stock",
)
def adjust_stock(
    adjustments: List[StockAdjustment],
    session: Session = Depends(get_session),
):
    """
    Add stock to multiple products.

    Business rules:
    - Product must exist.
    - Quantity must be greater than zero.
    - New stock cannot exceed 5,000.
    - Successful and failed operations are reported.
    """

    successful_updates = []

    failed_updates = []

    # --------------------------------------------------------
    # Process each adjustment
    # --------------------------------------------------------

    for adjustment in adjustments:

        # ----------------------------------------------------
        # 1. Check product exists
        # ----------------------------------------------------

        product = session.get(
            Product,
            adjustment.product_id,
        )

        if product is None:

            failed_updates.append(
                {
                    "product_id": (
                        adjustment.product_id
                    ),
                    "quantity_to_add": (
                        adjustment.quantity_to_add
                    ),
                    "reason": (
                        "Product not found"
                    ),
                }
            )

            continue

        # ----------------------------------------------------
        # 2. Calculate new stock
        # ----------------------------------------------------

        old_stock = product.stock

        new_stock = (
            old_stock
            + adjustment.quantity_to_add
        )

        # ----------------------------------------------------
        # 3. Check maximum stock
        # ----------------------------------------------------

        if new_stock > 5000:

            failed_updates.append(
                {
                    "product_id": product.id,
                    "product_name": product.name,
                    "current_stock": old_stock,
                    "quantity_to_add": (
                        adjustment.quantity_to_add
                    ),
                    "calculated_stock": new_stock,
                    "reason": (
                        "Stock cannot exceed "
                        "5,000 units"
                    ),
                }
            )

            continue

        # ----------------------------------------------------
        # 4. Update stock
        # ----------------------------------------------------

        product.stock = new_stock

        product.updated_at = datetime.utcnow()

        # ----------------------------------------------------
        # 5. Add to successful updates
        # ----------------------------------------------------

        successful_updates.append(
            {
                "product_id": product.id,
                "product_name": product.name,
                "old_stock": old_stock,
                "quantity_added": (
                    adjustment.quantity_to_add
                ),
                "new_stock": new_stock,
            }
        )

    # --------------------------------------------------------
    # 6. Commit successful updates
    # --------------------------------------------------------

    session.commit()

    # --------------------------------------------------------
    # 7. Log operation
    # --------------------------------------------------------

    logger.info(
        "Stock adjustment completed: "
        f"Successful={len(successful_updates)}, "
        f"Failed={len(failed_updates)}"
    )

    # --------------------------------------------------------
    # 8. Return summary
    # --------------------------------------------------------

    return {
        "success": True,
        "message": (
            "Stock adjustment completed"
        ),
        "successful_count": len(
            successful_updates
        ),
        "failed_count": len(
            failed_updates
        ),
        "successful_updates": (
            successful_updates
        ),
        "failed_updates": (
            failed_updates
        ),
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get(
    "/health",
)
def health_check():
    """
    Simple API health check.
    """

    return {
        "success": True,
        "message": (
            "TechVault Inventory API "
            "is running"
        ),
        "timestamp": datetime.utcnow().isoformat(),
    }
