from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "backend"."users" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "email" VARCHAR(255) NOT NULL UNIQUE,
    "hashed_password" VARCHAR(255) NOT NULL,
    "is_active" BOOL NOT NULL DEFAULT True,
    "is_superuser" BOOL NOT NULL DEFAULT False,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS "idx_users_email_133a6f" ON "backend"."users" ("email");
        CREATE TABLE IF NOT EXISTS "backend"."company_users" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "role" VARCHAR(20) NOT NULL DEFAULT 'viewer',
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "company_id" INT NOT NULL REFERENCES "backend"."companies" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "backend"."users" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_company_use_user_id_d47ba5" UNIQUE ("user_id", "company_id")
);
COMMENT ON COLUMN "backend"."company_users"."role" IS 'OWNER: owner\nADMIN: admin\nVIEWER: viewer';
        CREATE TABLE IF NOT EXISTS "backend"."refresh_tokens" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "jti" VARCHAR(64) NOT NULL UNIQUE,
    "expires_at" TIMESTAMPTZ NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "backend"."users" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_refresh_tok_jti_292326" ON "backend"."refresh_tokens" ("jti");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "backend"."company_users";
        DROP TABLE IF EXISTS "backend"."refresh_tokens";
        DROP TABLE IF EXISTS "backend"."users";"""


MODELS_STATE = (
    "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"
    "OvT2tRhI35d0qcVDWvXn78HxrXr4o="
)
