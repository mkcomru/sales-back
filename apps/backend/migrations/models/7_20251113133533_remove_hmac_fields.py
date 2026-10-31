from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."telegram_bots" DROP COLUMN "transport_signature_header";
        ALTER TABLE "backend"."telegram_bots" DROP COLUMN "transport_timestamp_header";
        ALTER TABLE "backend"."telegram_bots" DROP COLUMN "transport_algorithm";
        ALTER TABLE "backend"."telegram_bots" DROP COLUMN "transport_timestamp_tolerance_s";
        ALTER TABLE "backend"."telegram_bots" DROP COLUMN "transport_shared_secret";"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."telegram_bots" ADD "transport_signature_header" VARCHAR(100) NOT NULL DEFAULT 'X-Transport-Signature';
        ALTER TABLE "backend"."telegram_bots" ADD "transport_timestamp_header" VARCHAR(100) NOT NULL DEFAULT 'X-Transport-Timestamp';
        ALTER TABLE "backend"."telegram_bots" ADD "transport_algorithm" VARCHAR(16) NOT NULL DEFAULT 'HS256';
        ALTER TABLE "backend"."telegram_bots" ADD "transport_timestamp_tolerance_s" INT NOT NULL DEFAULT 300;
        ALTER TABLE "backend"."telegram_bots" ADD "transport_shared_secret" VARCHAR(255) NOT NULL;"""


MODELS_STATE = (
    "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"
)
