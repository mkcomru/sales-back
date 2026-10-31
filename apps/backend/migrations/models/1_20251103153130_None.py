from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE SCHEMA IF NOT EXISTS backend;

        CREATE TABLE IF NOT EXISTS "backend"."companies" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "name" VARCHAR(255) NOT NULL,
            "description" TEXT NOT NULL,
            "rules" TEXT NOT NULL,
            "tone_of_voice" TEXT NOT NULL,
            "collection_name" VARCHAR(255) NOT NULL,
            "stages_config" JSONB NOT NULL,
            "product_rules" JSONB NOT NULL,
            "bitrix_forward_metadata_keys" JSONB NOT NULL,
            "bitrix_default_stage_id" VARCHAR(50) NOT NULL DEFAULT 'PROCESSED'
        );

        COMMENT ON COLUMN "backend"."companies"."collection_name" IS
        E'The name of the collection in qdrant';

        CREATE TABLE IF NOT EXISTS "backend"."faqs" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "category" VARCHAR(255) NOT NULL,
            "question" TEXT NOT NULL,
            "answer" TEXT NOT NULL,
            "keywords" JSONB NOT NULL,
            "company_id" INT NOT NULL REFERENCES "backend"."companies" ("id")
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS "backend"."fields" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "name" VARCHAR(255) NOT NULL,
            "question" TEXT NOT NULL,
            "type" VARCHAR(255) NOT NULL,
            "required" BOOL NOT NULL DEFAULT False,
            "company_id" INT NOT NULL REFERENCES "backend"."companies" ("id")
                ON DELETE CASCADE
        );

        COMMENT ON COLUMN "backend"."fields"."type" IS
        E'STRING: string\nNUMBER: number\nBOOLEAN: boolean\nENUM: enum';

        CREATE TABLE IF NOT EXISTS "backend"."field_options" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "value" VARCHAR(255) NOT NULL,
            "order" INT NOT NULL DEFAULT 0,
            "field_id" INT NOT NULL REFERENCES "backend"."fields" ("id")
                ON DELETE CASCADE,
            CONSTRAINT "uid_field_optio_field_i_d55c4a"
                UNIQUE ("field_id", "value"),
            CONSTRAINT "uid_field_optio_field_i_df7c0a"
                UNIQUE ("field_id", "order")
        );

        CREATE TABLE IF NOT EXISTS "backend"."products" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "name" VARCHAR(255) NOT NULL,
            "description" TEXT NOT NULL,
            "guidelines" TEXT NOT NULL,
            "fewshots" JSONB NOT NULL,
            "product_key" VARCHAR(255) NOT NULL UNIQUE,
            "fields_config" JSONB NOT NULL,
            "geo_config" JSONB NOT NULL,
            "handoff_config" JSONB NOT NULL,
            "tools_qualifier" JSONB NOT NULL,
            "tools_product" JSONB NOT NULL,
            "companies_id" INT NOT NULL REFERENCES "backend"."companies" ("id")
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS "backend"."prompts" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "agent_type" VARCHAR(50) NOT NULL UNIQUE,
            "content" TEXT NOT NULL
        );

        COMMENT ON COLUMN "backend"."prompts"."agent_type" IS
        E'ROUTER: router\nQUALIFIER: qualifier\nPRODUCT_EXPERT: product_expert';

        CREATE TABLE IF NOT EXISTS "backend"."aerich" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "version" VARCHAR(255) NOT NULL,
            "app" VARCHAR(100) NOT NULL,
            "content" JSONB NOT NULL
        );
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """


MODELS_STATE = (
    "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"
    "+16j"
)
