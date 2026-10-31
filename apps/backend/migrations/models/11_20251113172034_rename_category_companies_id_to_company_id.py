from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."categories" DROP CONSTRAINT IF EXISTS "fk_categori_companie_2fafa35f";
        ALTER TABLE "backend"."categories" RENAME COLUMN "companies_id" TO "company_id";
        ALTER TABLE "backend"."categories" ADD CONSTRAINT "fk_categori_companie_c30653c3" FOREIGN KEY ("company_id") REFERENCES "backend"."companies" ("id") ON DELETE CASCADE;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."categories" DROP CONSTRAINT IF EXISTS "fk_categori_companie_c30653c3";
        ALTER TABLE "backend"."categories" RENAME COLUMN "company_id" TO "companies_id";
        ALTER TABLE "backend"."categories" ADD CONSTRAINT "fk_categori_companie_2fafa35f" FOREIGN KEY ("companies_id") REFERENCES "backend"."companies" ("id") ON DELETE CASCADE;"""


MODELS_STATE = (
    "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"
    "nzAJJefv7QiTUKRJUsYk2b56efoPvyqKlQ=="
)
