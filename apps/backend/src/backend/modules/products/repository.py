from src.backend.modules.core.base_repo import BaseRepository
from src.backend.modules.products.models import Product


class ProductsRepository(BaseRepository[Product]):
    def __init__(self):
        super().__init__(Product)

    async def get_by_id(self, product_id: int) -> Product | None:
        return await Product.get_or_none(id=product_id).prefetch_related("category")

    async def get_by_category(self, category_id: int) -> list[Product]:
        return await Product.filter(category_id=category_id).all()

    async def create(self, category_id: int, **kwargs) -> Product:
        return await Product.create(category_id=category_id, **kwargs)

    async def list_all(self) -> list[Product]:
        return await Product.all().prefetch_related("category")

    async def list_by_company_id(self, company_id: int) -> list[Product]:
        return await Product.filter(category__company_id=company_id).prefetch_related("category").all()

    async def update(self, product_id: int, updates: dict) -> Product | None:
        return await self._update(id=product_id, updates=updates)

    async def delete(self, product_id: int) -> bool:
        return await self._delete(id=product_id)
