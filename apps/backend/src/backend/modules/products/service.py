from src.backend.modules.products.exceptions import ProductNotFoundError
from src.backend.modules.products.models import Product
from src.backend.modules.products.repository import ProductsRepository
from src.backend.modules.products.schemas import ProductDetailResponse, ProductPatch, ProductRequest


class ProductsService:
    repository: ProductsRepository = ProductsRepository()

    def __init__(self, integration: object | None = None) -> None:
        pass

    async def list_for_agent(self, category_ids: list[int]) -> list[dict]:
        products = await Product.filter(category_id__in=category_ids).prefetch_related("category").all()
        return [
            ProductDetailResponse(
                id=p.id,
                name=p.name,
                description=p.description,
                category_id=p.category.id if p.category else None,
                attributes=p.attributes,
            ).model_dump()
            for p in products
        ]

    async def get_product_by_id(self, product_id: int) -> Product:
        product = await self.repository.get_by_id(product_id)

        if not product:
            raise ProductNotFoundError()

        return product

    async def create_product(self, payload: ProductRequest) -> Product:
        product_data = payload.model_dump(exclude={"category_id"})
        return await self.repository.create(category_id=payload.category_id, **product_data)

    async def delete_product(self, product_id: int) -> bool:
        deleted = await self.repository.delete(product_id)

        if not deleted:
            raise ProductNotFoundError()

        return True

    async def list_available_products(self) -> list[Product]:
        return await self.repository.list_all()

    async def list_products_for_company(self, company_id: int) -> list[Product]:
        return await self.repository.list_by_company_id(company_id)

    async def get_products_by_category(self, category_id: int) -> list[Product]:
        return await self.repository.get_by_category(category_id)

    async def update_product(self, product_id: int, payload: ProductPatch) -> Product:
        updates = payload.model_dump(exclude_unset=True, exclude_none=True)
        product = await self.repository.update(product_id, updates)

        if not product:
            raise ProductNotFoundError()

        return product
