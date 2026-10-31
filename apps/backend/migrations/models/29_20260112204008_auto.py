from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "backend"."company_balances" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "company_id" INT NOT NULL UNIQUE REFERENCES "backend"."companies" ("id") ON DELETE CASCADE,
    "balance" INT NOT NULL DEFAULT 0 CHECK ("balance" >= 0),
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS "idx_company_bal_company_74bd87" ON "backend"."company_balances" ("company_id");

CREATE TABLE IF NOT EXISTS "backend"."balance_ledger" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "company_id" INT NOT NULL REFERENCES "backend"."companies" ("id") ON DELETE CASCADE,
    "operation_type" VARCHAR(20) NOT NULL,
    "amount" INT NOT NULL,
    "timestamp" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "initiated_by" VARCHAR(20) NOT NULL,
    "operator_id" INT REFERENCES "backend"."company_users" ("id") ON DELETE SET NULL,
    "comment" TEXT,
    "thread_id" INT REFERENCES "backend"."threads" ("id") ON DELETE SET NULL,
    "channel_type" VARCHAR(50),
    "conversation_id" VARCHAR(255)
);
CREATE INDEX IF NOT EXISTS "idx_balance_led_company_0b6f44" ON "backend"."balance_ledger" ("company_id", "timestamp");
CREATE INDEX IF NOT EXISTS "idx_balance_led_thread__deca2a" ON "backend"."balance_ledger" ("thread_id");

ALTER TABLE "backend"."threads" ADD "billing_status" VARCHAR(20) NOT NULL DEFAULT 'active';
ALTER TABLE "backend"."threads" ADD "charged_at" TIMESTAMPTZ;

INSERT INTO "backend"."company_balances" ("company_id", "balance", "updated_at")
SELECT "id", 0, CURRENT_TIMESTAMP
FROM "backend"."companies"
ON CONFLICT ("company_id") DO NOTHING;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."threads" DROP COLUMN "charged_at";
        ALTER TABLE "backend"."threads" DROP COLUMN "billing_status";

        DROP INDEX IF EXISTS "idx_balance_led_thread__deca2a";
        DROP INDEX IF EXISTS "idx_balance_led_company_0b6f44";
        DROP TABLE IF EXISTS "backend"."balance_ledger";

        DROP INDEX IF EXISTS "idx_company_bal_company_74bd87";
        DROP TABLE IF EXISTS "backend"."company_balances";"""


MODELS_STATE = (
    "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"
)
