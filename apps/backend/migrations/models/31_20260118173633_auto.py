from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "backend"."orders" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "order_number" INT NOT NULL,
    "name" VARCHAR(255),
    "stage" VARCHAR(30) NOT NULL DEFAULT 'new',
    "order_fields" JSONB NOT NULL,
    "initial_channel" VARCHAR(50),
    "result" VARCHAR(10),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "closed_at" TIMESTAMPTZ,
    "assignee_id" INT REFERENCES "backend"."company_users" ("id") ON DELETE SET NULL,
    "company_id" INT NOT NULL REFERENCES "backend"."companies" ("id") ON DELETE CASCADE,
    "customer_id" INT NOT NULL REFERENCES "backend"."customers" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_orders_company_0ba8ea" UNIQUE ("company_id", "order_number")
);
CREATE INDEX IF NOT EXISTS "idx_orders_custome_52fa53" ON "backend"."orders" ("customer_id", "closed_at");
COMMENT ON COLUMN "backend"."orders"."stage" IS 'NEW: new\nQUALIFICATION: qualification\nOFFER: offer\nNEGOTIATION: negotiation\nCLOSED: closed';
COMMENT ON COLUMN "backend"."orders"."result" IS 'WON: won\nLOST: lost';
COMMENT ON TABLE "backend"."orders" IS 'Order/deal entity representing a business transaction.';
        COMMENT ON COLUMN "backend"."chat_messages"."type" IS 'TEXT: text
INTERNAL_NOTE: internal_note
SYSTEM_EVENT: system_event';
        ALTER TABLE "backend"."threads" ADD "active_order_id" INT;
        ALTER TABLE "backend"."threads" ADD CONSTRAINT "fk_threads_orders_59267e95" FOREIGN KEY ("active_order_id") REFERENCES "backend"."orders" ("id") ON DELETE SET NULL;
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."threads" DROP CONSTRAINT IF EXISTS "fk_threads_orders_59267e95";
        ALTER TABLE "backend"."threads" DROP COLUMN "active_order_id";
        COMMENT ON COLUMN "backend"."chat_messages"."type" IS 'TEXT: text
AUDIO: audio
IMAGE: image
VIDEO: video
INTERNAL_NOTE: internal_note
SYSTEM_EVENT: system_event';
        DROP TABLE IF EXISTS "backend"."orders";"""


MODELS_STATE = (
    "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"
    "Pbt1pvVpze22Mf1OCfNZ89vLr/8DwS3Uaw=="
)
