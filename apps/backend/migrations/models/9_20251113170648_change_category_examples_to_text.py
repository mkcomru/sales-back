from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."categories" ADD COLUMN "examples_new" TEXT DEFAULT '';
        UPDATE "backend"."categories" SET "examples_new" = 
            CASE 
                WHEN jsonb_typeof("examples") = 'array' THEN 
                    array_to_string(
                        ARRAY(SELECT jsonb_array_elements_text("examples")),
                        E'\\n\\n'
                    )
                ELSE 
                    COALESCE("examples"::TEXT, '')
            END;
        ALTER TABLE "backend"."categories" DROP COLUMN "examples";
        ALTER TABLE "backend"."categories" RENAME COLUMN "examples_new" TO "examples";
        ALTER TABLE "backend"."categories" ALTER COLUMN "examples" SET DEFAULT '';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."categories" ADD COLUMN "examples_old" JSONB DEFAULT '[]'::JSONB;
        UPDATE "backend"."categories" SET "examples_old" = 
            CASE 
                WHEN "examples" = '' THEN '[]'::JSONB
                ELSE jsonb_build_array("examples")
            END;
        ALTER TABLE "backend"."categories" DROP COLUMN "examples";
        ALTER TABLE "backend"."categories" RENAME COLUMN "examples_old" TO "examples";
        ALTER TABLE "backend"."categories" ALTER COLUMN "examples" SET DEFAULT '[]'::JSONB;"""


MODELS_STATE = (
    "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"
    "lMiTUBQlqUJJVm9env4HrAMYhw=="
)
