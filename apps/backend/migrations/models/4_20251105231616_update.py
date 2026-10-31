from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "backend"."tools" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "name" VARCHAR(100) NOT NULL UNIQUE,
            "description" TEXT NOT NULL,
            "arguments" JSONB NOT NULL,
            "required" BOOL NOT NULL DEFAULT False
        );
        ALTER TABLE "backend"."categories" DROP COLUMN IF EXISTS "tools";
        ALTER TABLE "backend"."companies" DROP COLUMN IF EXISTS "qualifier_tools";
        CREATE TABLE "backend"."company_tools" (
            "tools_id" INT NOT NULL REFERENCES "backend"."tools" ("id")
                ON DELETE CASCADE,
            "company_id" INT NOT NULL REFERENCES "backend"."companies" ("id")
                ON DELETE CASCADE
        );
        CREATE TABLE "backend"."category_tools" (
            "category_id" INT NOT NULL REFERENCES "backend"."categories" ("id")
                ON DELETE CASCADE,
            "tools_id" INT NOT NULL REFERENCES "backend"."tools" ("id")
                ON DELETE CASCADE
        );
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "backend"."category_tools";
        DROP TABLE IF EXISTS "backend"."company_tools";
        ALTER TABLE "backend"."companies" ADD "qualifier_tools" JSONB NOT NULL;
        ALTER TABLE "backend"."categories" ADD "tools" JSONB NOT NULL;
        DROP TABLE IF EXISTS "backend"."company_tools";
        DROP TABLE IF EXISTS "backend"."category_tools";
        DROP TABLE IF EXISTS "backend"."tools";
    """


MODELS_STATE = (
    "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"
)
