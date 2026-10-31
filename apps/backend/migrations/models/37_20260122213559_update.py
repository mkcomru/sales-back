from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "backend"."stage_templates" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL,
    "color" VARCHAR(7),
    "position" INT NOT NULL,
    "is_final" BOOL NOT NULL DEFAULT False,
    "result" VARCHAR(10),
    "auto_close" BOOL NOT NULL DEFAULT False,
    "transition_condition" JSONB,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "company_id" INT NOT NULL REFERENCES "backend"."companies" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_stage_templ_company_fa8b7f" UNIQUE ("company_id", "position")
);
CREATE INDEX IF NOT EXISTS "idx_stage_templ_company_fa8b7f" ON "backend"."stage_templates" ("company_id", "position");
COMMENT ON COLUMN "backend"."stage_templates"."result" IS 'WON: won\nLOST: lost';
COMMENT ON TABLE "backend"."stage_templates" IS 'Stage template for custom sales funnel stages.';
        ALTER TABLE "backend"."orders" ADD "stage_id" INT;
        ALTER TABLE "backend"."orders" ADD "frozen" BOOL NOT NULL DEFAULT False;
        ALTER TABLE "backend"."orders" DROP COLUMN "stage";
        ALTER TABLE "backend"."orders" ADD CONSTRAINT "fk_orders_stage_te_184061bf" FOREIGN KEY ("stage_id") REFERENCES "backend"."stage_templates" ("id") ON DELETE SET NULL;
        CREATE INDEX IF NOT EXISTS "idx_orders_company_5621de" ON "backend"."orders" ("company_id", "stage_id", "frozen", "closed_at");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_orders_company_5621de";
        ALTER TABLE "backend"."orders" DROP CONSTRAINT IF EXISTS "fk_orders_stage_te_184061bf";
        ALTER TABLE "backend"."orders" ADD "stage" VARCHAR(30) NOT NULL DEFAULT 'new';
        ALTER TABLE "backend"."orders" DROP COLUMN "stage_id";
        ALTER TABLE "backend"."orders" DROP COLUMN "frozen";
        COMMENT ON COLUMN "backend"."orders"."stage" IS 'NEW: new\nQUALIFICATION: qualification\nOFFER: offer\nNEGOTIATION: negotiation\nCLOSED: closed';
        DROP TABLE IF EXISTS "backend"."stage_templates";"""


MODELS_STATE = (
    "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"
)
