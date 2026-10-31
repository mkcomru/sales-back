from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "backend"."company_tools";
        DROP TABLE IF EXISTS "backend"."category_tools";
        CREATE TABLE IF NOT EXISTS "backend"."category_tools" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "category_id" INT NOT NULL REFERENCES "backend"."categories" ("id") ON DELETE CASCADE,
    "tool_id" INT NOT NULL REFERENCES "backend"."tools" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_category_to_categor_a48e23" UNIQUE ("category_id", "tool_id")
);
COMMENT ON TABLE "backend"."category_tools" IS 'Through table for Category-Tool ManyToMany relation.';
        CREATE TABLE IF NOT EXISTS "backend"."company_tools" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "company_id" INT NOT NULL REFERENCES "backend"."companies" ("id") ON DELETE CASCADE,
    "tool_id" INT NOT NULL REFERENCES "backend"."tools" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_company_too_company_165641" UNIQUE ("company_id", "tool_id")
);
COMMENT ON TABLE "backend"."company_tools" IS 'Through table for Company-Tool ManyToMany relation.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "backend"."company_tools";
        DROP TABLE IF EXISTS "backend"."category_tools";
        CREATE TABLE "backend"."company_tools" (
    "tools_id" INT NOT NULL REFERENCES "backend"."tools" ("id") ON DELETE CASCADE,
    "company_id" INT NOT NULL REFERENCES "backend"."companies" ("id") ON DELETE CASCADE
);
        CREATE TABLE "backend"."category_tools" (
    "category_id" INT NOT NULL REFERENCES "backend"."categories" ("id") ON DELETE CASCADE,
    "tools_id" INT NOT NULL REFERENCES "backend"."tools" ("id") ON DELETE CASCADE
);"""


MODELS_STATE = (
    "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"
    "g1DkpEQehKIoSR1Ksvrt5el/CzEmwQ=="
)
