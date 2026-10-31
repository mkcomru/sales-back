from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "backend"."connectors" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "connector_id" VARCHAR(100) NOT NULL UNIQUE,
    "type" VARCHAR(20) NOT NULL,
    "channel_type" VARCHAR(50) NOT NULL,
    "display_name" VARCHAR(255) NOT NULL,
    "managed" BOOL NOT NULL DEFAULT True,
    "config" JSONB NOT NULL,
    "enabled" BOOL NOT NULL DEFAULT True,
    "debounce_window_seconds" INT NOT NULL DEFAULT 45,
    "debounce_storage_key_template" VARCHAR(255) NOT NULL DEFAULT '{connector_id}:{conversation_id}',
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "company_id" INT NOT NULL REFERENCES "backend"."companies" ("id") ON DELETE CASCADE
);
COMMENT ON COLUMN "backend"."connectors"."type" IS 'TELEGRAM: telegram\nWAPPI: wappi\nCUSTOM: custom';
COMMENT ON TABLE "backend"."connectors" IS 'Unified connector model replacing separate TelegramBot/WappiConnector tables.';
        CREATE TABLE IF NOT EXISTS "backend"."connector_api_keys" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "key_hash" VARCHAR(64) NOT NULL UNIQUE,
    "enabled" BOOL NOT NULL DEFAULT True,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "connector_id" INT NOT NULL REFERENCES "backend"."connectors" ("id") ON DELETE CASCADE
);
COMMENT ON TABLE "backend"."connector_api_keys" IS 'API key for custom (unmanaged) connectors.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "backend"."connector_api_keys";
        DROP TABLE IF EXISTS "backend"."connectors";"""


MODELS_STATE = (
    "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"
    "VKHi"
)
