from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "backend"."customers" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "user_id" VARCHAR(64) NOT NULL UNIQUE,
    "rejected" BOOL NOT NULL DEFAULT False,
    "rejection_reason" VARCHAR(255),
    "quiz_answers" JSONB NOT NULL DEFAULT '{}',
    "langfuse_sessions" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "company_id" INT NOT NULL REFERENCES "backend"."companies" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_customers_user_id_a179cb" ON "backend"."customers" ("user_id");
COMMENT ON TABLE "backend"."customers" IS 'Customer profile with quiz answers and conversation metadata.';
        CREATE TABLE IF NOT EXISTS "backend"."threads" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "thread_id" VARCHAR(128) NOT NULL UNIQUE,
    "channel_type" VARCHAR(50) NOT NULL,
    "conversation_id" VARCHAR(255),
    "state" VARCHAR(30) NOT NULL DEFAULT 'active',
    "assistant_active" BOOL NOT NULL DEFAULT True,
    "metadata" JSONB NOT NULL DEFAULT '{}',
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
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "attachments" JSONB NOT NULL DEFAULT '[]',
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
COMMENT ON TABLE "backend"."chat_messages" IS 'Individual message within a thread.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "backend"."chat_messages";
        DROP TABLE IF EXISTS "backend"."threads";
        DROP TABLE IF EXISTS "backend"."customers";"""


MODELS_STATE = (
    "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"
    "Iq"
)
