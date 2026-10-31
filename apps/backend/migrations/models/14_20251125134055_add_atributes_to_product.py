from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."products" ADD "attributes" JSONB NOT NULL DEFAULT '{}';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."products" DROP COLUMN "attributes";"""


MODELS_STATE = (
    "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"
)
