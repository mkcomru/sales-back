from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "backend"."wappi_connectors" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "connector_id" VARCHAR(100) NOT NULL UNIQUE,
    "channel_type" VARCHAR(50) NOT NULL,
    "metadata" JSONB NOT NULL,
    "wappi_token" VARCHAR(255),
    "wappi_profile_id" VARCHAR(255),
    "transport_endpoint" VARCHAR(255),
    "enabled" BOOL NOT NULL DEFAULT True,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "company_id" INT NOT NULL REFERENCES "backend"."companies" ("id") ON DELETE CASCADE
);
        ALTER TABLE "backend"."tools" DROP COLUMN "arguments";"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."tools" ADD "arguments" JSONB NOT NULL;
        DROP TABLE IF EXISTS "backend"."wappi_connectors";"""


MODELS_STATE = (
    "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"
    "r3dqfv0HcSJTnw=="
)
