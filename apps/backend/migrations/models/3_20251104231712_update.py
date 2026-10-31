from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."categories"
            RENAME COLUMN "product_search_config" TO "tools";
        ALTER TABLE "backend"."categories" ADD "workflow" TEXT NOT NULL;
        ALTER TABLE "backend"."companies" ADD "qualification_workflow" TEXT NOT NULL;
        ALTER TABLE "backend"."companies" ADD "qualification_examples" TEXT NOT NULL;
        ALTER TABLE "backend"."companies" ADD "assistant_name" VARCHAR(255) NOT NULL;
        ALTER TABLE "backend"."companies" ADD "qualifier_tools" JSONB NOT NULL;
        ALTER TABLE "backend"."fields" RENAME COLUMN "type" TO "answer_type";
        ALTER TABLE "backend"."products" DROP COLUMN "guidelines";
        ALTER TABLE "backend"."products" DROP COLUMN "tools_qualifier";
        ALTER TABLE "backend"."products" DROP COLUMN "tools_product";
        ALTER TABLE "backend"."products" DROP COLUMN "fewshots";
        COMMENT ON COLUMN "backend"."prompts"."agent_type" IS
        E'ROUTER: router\nQUALIFIER: qualifier\nCATEGORY_EXPERT: category_expert';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."fields" RENAME COLUMN "answer_type" TO "type";
        COMMENT ON COLUMN "backend"."prompts"."agent_type" IS
        E'ROUTER: router\nQUALIFIER: qualifier\nPRODUCT_EXPERT: product_expert';
        ALTER TABLE "backend"."companies" DROP COLUMN "qualification_workflow";
        ALTER TABLE "backend"."companies" DROP COLUMN "qualification_examples";
        ALTER TABLE "backend"."companies" DROP COLUMN "assistant_name";
        ALTER TABLE "backend"."companies" DROP COLUMN "qualifier_tools";
        ALTER TABLE "backend"."products" ADD "guidelines" TEXT NOT NULL;
        ALTER TABLE "backend"."products" ADD "tools_qualifier" JSONB NOT NULL;
        ALTER TABLE "backend"."products" ADD "tools_product" JSONB NOT NULL;
        ALTER TABLE "backend"."products" ADD "fewshots" JSONB NOT NULL;
        ALTER TABLE "backend"."categories"
            RENAME COLUMN "tools" TO "product_search_config";
        ALTER TABLE "backend"."categories" DROP COLUMN "workflow";
    """


MODELS_STATE = (
    "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"
)
