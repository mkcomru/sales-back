from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from src.backend.modules.products.models import Product


class ProductBase(BaseModel):
    name: str
    description: str
    attributes: dict = Field(default_factory=dict)


class ProductRequest(ProductBase):
    category_id: int


class ProductResponse(ProductBase):
    id: int
    category_id: int

    @classmethod
    def from_model(cls, product: "Product") -> "ProductResponse":
        """Convert Product model to ProductResponse. Expects category prefetched."""
        if product.category is None:
            raise ValueError("Product must belong to a category")
        return cls(
            id=product.id,
            name=product.name,
            description=product.description,
            attributes=product.attributes,
            category_id=product.category.id,
        )


class ProductPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    category_id: int | None = None
    attributes: dict | None = None


class ProductDetailResponse(BaseModel):
    """Детальная информация о продукте для Sales Agent"""

    id: int
    name: str
    description: str
    category_id: int | None = None
    attributes: dict = Field(default_factory=dict)
