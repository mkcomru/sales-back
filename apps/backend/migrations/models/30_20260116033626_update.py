from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."chat_messages" ADD "artifact_ids" JSONB DEFAULT '[]'::jsonb;
        UPDATE "backend"."chat_messages" SET "artifact_ids" = '[]'::jsonb WHERE "artifact_ids" IS NULL;
        ALTER TABLE "backend"."chat_messages" ALTER COLUMN "artifact_ids" SET NOT NULL;
        COMMENT ON COLUMN "backend"."chat_messages"."type" IS 'TEXT: text
AUDIO: audio
IMAGE: image
VIDEO: video
INTERNAL_NOTE: internal_note
SYSTEM_EVENT: system_event';
        ALTER TABLE "backend"."company_balances" ADD CONSTRAINT "fk_company__companie_87ddabb1" FOREIGN KEY ("company_id") REFERENCES "backend"."companies" ("id") ON DELETE CASCADE;
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_company_bal_company_74bd87" ON "backend"."company_balances" ("company_id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."company_balances" DROP CONSTRAINT IF EXISTS "company_balances_company_id_key";
        DROP INDEX IF EXISTS "uid_company_bal_company_74bd87";
        ALTER TABLE "backend"."company_balances" DROP CONSTRAINT IF EXISTS "fk_company__companie_87ddabb1";
        ALTER TABLE "backend"."chat_messages" DROP COLUMN "artifact_ids";
        COMMENT ON COLUMN "backend"."chat_messages"."type" IS 'TEXT: text
INTERNAL_NOTE: internal_note
SYSTEM_EVENT: system_event';
        ALTER TABLE "backend"."company_balances" ADD CONSTRAINT "fk_company__companie_87ddabb1" FOREIGN KEY ("company_id") REFERENCES "backend"."companies" ("id") ON DELETE CASCADE;
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_company_bal_company_74bd87" ON "backend"."company_balances" ("company_id");"""


MODELS_STATE = (
    "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"
    "5y6lam7rY3q09rYbeN2XcquM+a315+/z9CkcuY"
)
