from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_threads_custome_d0f38a";
        DROP INDEX IF EXISTS "idx_chat_messag_thread__74994e";
        ALTER TABLE "backend"."customers" ADD "name" VARCHAR(255);
        ALTER TABLE "backend"."threads" ADD "unread_count" INT NOT NULL DEFAULT 0;
        ALTER TABLE "backend"."threads" ADD "assignee_id" INT;
        CREATE INDEX IF NOT EXISTS "idx_chat_messag_thread__74994e" ON "backend"."chat_messages" ("thread_id", "created_at");
        ALTER TABLE "backend"."threads" ADD CONSTRAINT "fk_threads_company__9ca6041d" FOREIGN KEY ("assignee_id") REFERENCES "backend"."company_users" ("id") ON DELETE CASCADE;
        CREATE INDEX IF NOT EXISTS "idx_threads_custome_d0f38a" ON "backend"."threads" ("customer_id", "channel_type");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_chat_messag_thread__74994e";
        DROP INDEX IF EXISTS "idx_threads_custome_d0f38a";
        ALTER TABLE "backend"."threads" DROP CONSTRAINT IF EXISTS "fk_threads_company__9ca6041d";
        ALTER TABLE "backend"."threads" DROP COLUMN "unread_count";
        ALTER TABLE "backend"."threads" DROP COLUMN "assignee_id";
        ALTER TABLE "backend"."customers" DROP COLUMN "name";
        CREATE INDEX IF NOT EXISTS "idx_threads_custome_d0f38a" ON "backend"."threads" ("customer_id", "channel_type");
        CREATE INDEX IF NOT EXISTS "idx_chat_messag_thread__74994e" ON "backend"."chat_messages" ("thread_id", "created_at");"""


MODELS_STATE = (
    "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"
    "//D45VAIg="
)
