from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."companies" RENAME COLUMN "bitrix_forward_metadata_keys" TO "crm_forward_metadata_keys";
        ALTER TABLE "backend"."companies" RENAME COLUMN "bitrix_default_stage_id" TO "crm_default_stage_id";
        ALTER TABLE "backend"."companies" ADD COLUMN "crm_manager_attention_stage_id" VARCHAR(50);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."companies" RENAME COLUMN "crm_default_stage_id" TO "bitrix_default_stage_id";
        ALTER TABLE "backend"."companies" RENAME COLUMN "crm_forward_metadata_keys" TO "bitrix_forward_metadata_keys";
        ALTER TABLE "backend"."companies" DROP COLUMN "crm_manager_attention_stage_id";"""


MODELS_STATE = (
    "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"
)
