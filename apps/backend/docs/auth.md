# Authentication System

## Overview

Backend implements JWT-based authentication for API clients. This system is **separate** from inter-service authentication (which uses `X-Service-Key`).

## Architecture

- **User Management**: Users are stored in `backend.users` table with email/password authentication.
- **Company Access**: Users can have access to multiple companies via `backend.company_users` with roles (`owner`, `admin`, `viewer`).
- **Token Types**:
  - **Access Token**: Short-lived (15 min default), passed in `Authorization: Bearer <token>` header.
  - **Refresh Token**: Long-lived (30 days default), used to obtain new access tokens.

## Models

### User
- `id`: Primary key
- `email`: Unique, indexed
- `hashed_password`: Bcrypt hash
- `is_active`: Account status
- `is_superuser`: Platform-wide admin flag

### CompanyUser
- Links `User` to `Company` with a specific role
- Roles: `owner` > `admin` > `viewer` (hierarchy for permission checks)

### RefreshToken
- Stores active refresh tokens with `jti` (JWT ID) for revocation
- Automatically cleaned up on expiration

## API Endpoints

### POST /auth/login
**Request:**
```json
{
  "email": "user@example.com",
  "password": "your_password_here"  # pragma: allowlist secret
}
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

### POST /auth/refresh
**Request:**
```json
{
  "refresh_token": "eyJ..."
}
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

Note: Old refresh token is automatically revoked (rotation).

### POST /auth/logout
**Request:**
```json
{
  "refresh_token": "eyJ..."
}
```

**Response:** `204 No Content`

### POST /auth/logout-all
Requires authentication. Revokes all refresh tokens for the current user.

**Response:** `204 No Content`

## Using Authentication in Routes

### Require Authenticated User
```python
from fastapi import Depends
from backend.api.dependencies import get_current_user
from backend.db.models import User

@router.get("/protected")
async def protected_route(
    current_user: Annotated[User, Depends(get_current_user)]
):
    return {"user_id": current_user.id}
```

### Require Superuser
```python
from backend.api.dependencies import require_superuser

@router.get("/admin-only")
async def admin_route(
    current_user: Annotated[User, Depends(require_superuser)]
):
    return {"message": "Admin access"}
```

### Require Company Role
```python
from backend.api.dependencies import require_company_role
from backend.db.models import CompanyUser, UserRole

@router.get("/companies/{company_id}/sensitive")
async def company_admin_route(
    company_id: int,
    company_user: Annotated[
        CompanyUser,
        Depends(lambda: require_company_role(company_id, required_role=UserRole.ADMIN))
    ]
):
    return {"company_id": company_id}
```

## Configuration

Environment variables (in `.env.shared` or `apps/backend/.env`):

```bash
# Required - keep this secret!
AUTH__JWT_SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_urlsafe(32))">

# Optional (defaults shown)
AUTH__JWT_ALGORITHM=HS256
AUTH__ACCESS_TOKEN_EXPIRE_MINUTES=15
AUTH__REFRESH_TOKEN_EXPIRE_DAYS=30
```

**Important:** `AUTH__JWT_SECRET_KEY` is required. The application will not start without it. This ensures token stability across restarts.

## Creating Users

### Superuser via CLI
```bash
cd apps/backend
uv run python -m backend.cli.create_superuser admin@example.com SecurePassword123
```

### Regular Users
Users should be created through backend API by superusers. No public registration endpoint exists.

## Service-to-Service vs User Authentication

- **Service calls** (e.g., telegram-module → backend): Use `X-Service-Key` header (existing pattern).
- **User calls** (e.g., API clients → backend): Use `Authorization: Bearer <access_token>`.

Do **not** mix these: JWT tokens are for human users, service key is for machines.

## Security Notes

- Passwords are hashed with bcrypt before storage.
- Access tokens are stateless (cannot be revoked individually).
- Refresh tokens can be revoked via database.
- Use HTTPS in production to protect tokens in transit.
- Keep `AUTH__JWT_SECRET_KEY` secret and rotate periodically.

## Future Extensions

When adding email/SMS verification:
- Add `UserContact` model (`email_verified_at`, `phone_verified_at`)
- Add `VerificationChallenge` model for one-time codes
- Extend `/auth/login` to return `mfa_required` + `challenge_id` when MFA is enabled
- Add `/auth/verify-mfa` endpoint for code submission

See `AGENTS.md` §7 for details on future MFA/passwordless flows.

