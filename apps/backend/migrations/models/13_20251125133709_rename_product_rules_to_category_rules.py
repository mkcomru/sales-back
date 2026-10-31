from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."companies" RENAME COLUMN "product_rules" TO "category_rules";"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."companies" RENAME COLUMN "category_rules" TO "product_rules";"""


MODELS_STATE = (
    "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"
)
