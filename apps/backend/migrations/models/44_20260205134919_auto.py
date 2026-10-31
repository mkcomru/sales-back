from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "backend"."prompt_addons" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL,
    "qualification_workflow" TEXT NOT NULL,
    "qualification_examples" TEXT NOT NULL,
    "company_id" INT NOT NULL REFERENCES "backend"."companies" ("id") ON DELETE CASCADE
);
COMMENT ON TABLE "backend"."prompt_addons" IS 'Prompt addon model.';
        CREATE TABLE IF NOT EXISTS "backend"."tasks" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "subject_type" VARCHAR(20) NOT NULL,
    "subject_id" INT NOT NULL,
    "title" VARCHAR(255) NOT NULL,
    "description" TEXT,
    "type" VARCHAR(20) NOT NULL,
    "due_date" TIMESTAMPTZ NOT NULL,
    "auto_action" VARCHAR(50),
    "completed" BOOL NOT NULL DEFAULT False,
    "completed_at" TIMESTAMPTZ,
    "completed_by_type" VARCHAR(20),
    "cancelled_at" TIMESTAMPTZ,
    "attempt_count" INT NOT NULL DEFAULT 0,
    "last_attempt_at" TIMESTAMPTZ,
    "failure_reason" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "assignee_id" INT REFERENCES "backend"."company_users" ("id") ON DELETE SET NULL,
    "company_id" INT NOT NULL REFERENCES "backend"."companies" ("id") ON DELETE CASCADE,
    "created_by_id" INT REFERENCES "backend"."company_users" ("id") ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS "idx_tasks_company_61acb9" ON "backend"."tasks" ("company_id", "subject_type", "subject_id");
CREATE INDEX IF NOT EXISTS "idx_tasks_due_dat_89d016" ON "backend"."tasks" ("due_date");
CREATE INDEX IF NOT EXISTS "idx_tasks_company_50eba5" ON "backend"."tasks" ("company_id", "assignee_id");
COMMENT ON COLUMN "backend"."tasks"."subject_type" IS 'ORDER: order';
COMMENT ON COLUMN "backend"."tasks"."type" IS 'MANUAL: manual\nAI_SCHEDULED: ai_scheduled';
COMMENT ON COLUMN "backend"."tasks"."auto_action" IS 'SEND_FOLLOWUP_MESSAGE: send_followup_message';
COMMENT ON COLUMN "backend"."tasks"."completed_by_type" IS 'USER: user\nSYSTEM: system';
COMMENT ON TABLE "backend"."tasks" IS 'Unified task entity with polymorphic subject binding.';
        ALTER TABLE "backend"."connectors" ADD "prompt_addon_id" INT;
        COMMENT ON COLUMN "backend"."order_logs"."type" IS 'ORDER_CREATED: order_created
STAGE_CHANGE: stage_change
ASSIGNEE_CHANGE: assignee_change
FIELD_CHANGE: field_change
COMMENT: comment
TASK_CREATED: task_created
TASK_COMPLETED: task_completed';
        ALTER TABLE "backend"."connectors" ADD CONSTRAINT "fk_connecto_prompt_a_a6159fc0" FOREIGN KEY ("prompt_addon_id") REFERENCES "backend"."prompt_addons" ("id") ON DELETE SET NULL;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."connectors" DROP CONSTRAINT IF EXISTS "fk_connecto_prompt_a_a6159fc0";
        COMMENT ON COLUMN "backend"."order_logs"."type" IS 'ORDER_CREATED: order_created
STAGE_CHANGE: stage_change
ASSIGNEE_CHANGE: assignee_change
FIELD_CHANGE: field_change
COMMENT: comment';
        ALTER TABLE "backend"."connectors" DROP COLUMN "prompt_addon_id";
        DROP TABLE IF EXISTS "backend"."tasks";
        DROP TABLE IF EXISTS "backend"."prompt_addons";"""


MODELS_STATE = (
    "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"
    "wHxW/fHy1/8DUg4V+A=="
)
