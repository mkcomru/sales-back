from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "backend"."threads" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "thread_id" VARCHAR(128) NOT NULL UNIQUE,
    "channel_type" VARCHAR(50) NOT NULL,
    "conversation_id" VARCHAR(255),
    "state" VARCHAR(30) NOT NULL DEFAULT 'active',
    "assistant_active" BOOL NOT NULL DEFAULT True,
    "metadata" JSONB NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "company_id" INT NOT NULL REFERENCES "backend"."companies" ("id") ON DELETE CASCADE,
    "customer_id" INT NOT NULL REFERENCES "backend"."customers" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_threads_thread__1d8cc8" ON "backend"."threads" ("thread_id");
CREATE INDEX IF NOT EXISTS "idx_threads_custome_d0f38a" ON "backend"."threads" ("customer_id", "channel_type");
COMMENT ON COLUMN "backend"."threads"."state" IS 'ACTIVE: active\nWAITING_ASSISTANT: waiting_assistant\nWAITING_MANAGER: waiting_manager\nHANDOFF: handoff\nCLOSED: closed';
COMMENT ON TABLE "backend"."threads" IS 'Conversation thread grouping messages from a specific channel.';
        CREATE TABLE IF NOT EXISTS "backend"."chat_messages" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "message_id" VARCHAR(128) NOT NULL UNIQUE,
    "role" VARCHAR(16) NOT NULL,
    "content" TEXT NOT NULL,
    "status" VARCHAR(20) NOT NULL DEFAULT 'pending',
    "metadata" JSONB NOT NULL,
    "attachments" JSONB NOT NULL,
    "reply_to" VARCHAR(128),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    "delivered_at" TIMESTAMPTZ,
    "thread_id" INT NOT NULL REFERENCES "backend"."threads" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_chat_messag_message_7a269e" ON "backend"."chat_messages" ("message_id");
CREATE INDEX IF NOT EXISTS "idx_chat_messag_thread__74994e" ON "backend"."chat_messages" ("thread_id", "created_at");
COMMENT ON COLUMN "backend"."chat_messages"."role" IS 'USER: user\nASSISTANT: assistant\nMANAGER: manager\nSYSTEM: system';
COMMENT ON COLUMN "backend"."chat_messages"."status" IS 'PENDING: pending\nSENT: sent\nFAILED: failed\nCANCELLED: cancelled';
COMMENT ON TABLE "backend"."chat_messages" IS 'Individual message within a thread.';
        ALTER TABLE "backend"."customers" DROP CONSTRAINT IF EXISTS "customers_user_id_key";
        ALTER TABLE "backend"."customers" DROP CONSTRAINT IF EXISTS "uid_customers_user_id_aebb98";
        ALTER TABLE "backend"."customers" ADD CONSTRAINT "uid_customers_user_id_aebb98" UNIQUE ("user_id", "company_id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."customers" DROP CONSTRAINT IF EXISTS "uid_customers_user_id_aebb98";
        ALTER TABLE "backend"."customers" ADD CONSTRAINT "customers_user_id_key" UNIQUE ("user_id");
        DROP TABLE IF EXISTS "backend"."threads";
        DROP TABLE IF EXISTS "backend"."chat_messages";"""


MODELS_STATE = (
    "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"
)
