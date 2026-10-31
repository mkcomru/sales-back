from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "backend"."telegram_bots" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "connector_id" VARCHAR(100) NOT NULL UNIQUE,
            "bot_token" VARCHAR(255) NOT NULL,
            "transport_shared_secret" VARCHAR(255) NOT NULL,
            "transport_signature_header" VARCHAR(100) NOT NULL DEFAULT 'X-Transport-Signature',
            "transport_timestamp_header" VARCHAR(100) NOT NULL DEFAULT 'X-Transport-Timestamp',
            "transport_timestamp_tolerance_s" INT NOT NULL DEFAULT 300,
            "transport_algorithm" VARCHAR(16) NOT NULL DEFAULT 'HS256',
            "mode" VARCHAR(20) NOT NULL DEFAULT 'auto',
            "channel_type" VARCHAR(50) NOT NULL DEFAULT 'telegram',
            "webhook_secret" VARCHAR(255),
            "webhook_path" VARCHAR(255),
            "metadata" JSONB NOT NULL,
            "enabled" BOOL NOT NULL DEFAULT TRUE,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "company_id" INT NOT NULL REFERENCES "backend"."companies" ("id") ON DELETE CASCADE
        );
        COMMENT ON COLUMN "backend"."telegram_bots"."mode" IS 'AUTO: auto
WEBHOOK: webhook
POLLING: polling';
        ALTER TABLE "backend"."tools" DROP COLUMN "required";
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."tools" ADD "required" BOOL NOT NULL DEFAULT False;
        DROP TABLE IF EXISTS "backend"."telegram_bots";"""


MODELS_STATE = (
    "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"
    "YdiFZ2SLGWDxGVnJ/3bA/wTby/O/Be5KVg=="
)
