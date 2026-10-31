from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        COMMENT ON COLUMN "backend"."chat_messages"."status" IS 'PENDING: pending
SENT: sent
DELIVERED: delivered
FAILED: failed
CANCELLED: cancelled';
        ALTER TABLE "backend"."fields" ADD "display_name" VARCHAR(255);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."fields" DROP COLUMN "display_name";
        COMMENT ON COLUMN "backend"."chat_messages"."status" IS 'PENDING: pending
SENT: sent
FAILED: failed
CANCELLED: cancelled';"""


MODELS_STATE = (
    "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"
)
