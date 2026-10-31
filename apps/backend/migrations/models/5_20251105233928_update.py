from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "backend"."category_tools";
        DROP TABLE IF EXISTS "backend"."company_tools";
        CREATE TABLE "backend"."company_tools" (
            "tools_id" INT NOT NULL REFERENCES "backend"."tools" ("id")
                ON DELETE CASCADE,
            "company_id" INT NOT NULL REFERENCES "backend"."companies" ("id")
                ON DELETE CASCADE
        );
        CREATE TABLE "backend"."category_tools" (
            "tools_id" INT NOT NULL REFERENCES "backend"."tools" ("id")
                ON DELETE CASCADE,
            "category_id" INT NOT NULL REFERENCES "backend"."categories" ("id")
                ON DELETE CASCADE
        );
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "backend"."category_tools";
        DROP TABLE IF EXISTS "backend"."company_tools";
        CREATE TABLE "backend"."company_tools" (
            "tools_id" INT NOT NULL REFERENCES "backend"."tools" ("id")
                ON DELETE CASCADE,
            "company_id" INT NOT NULL REFERENCES "backend"."companies" ("id")
                ON DELETE CASCADE
        );
        CREATE TABLE "backend"."category_tools" (
            "tools_id" INT NOT NULL REFERENCES "backend"."tools" ("id")
                ON DELETE CASCADE,
            "category_id" INT NOT NULL REFERENCES "backend"."categories" ("id")
                ON DELETE CASCADE
        );
    """


MODELS_STATE = (
    "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"
)
