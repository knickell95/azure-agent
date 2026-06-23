# LibreChat Integration Plan

## Prerequisites

This plan assumes [SESSION_HISTORY_AND_AUTH.md](SESSION_HISTORY_AND_AUTH.md) has been implemented. Several of those artifacts are superseded by LibreChat's built-in equivalents and will be removed as part of this plan.

---

## What LibreChat Replaces

| Previous plan artifact | LibreChat equivalent | Disposition |
|---|---|---|
| Blob Storage session store | LibreChat → MongoDB (Cosmos DB) | Remove `session_store.py` and the Azure Storage account |
| Container Apps EasyAuth (`authConfigs` Bicep resource) | LibreChat built-in OpenID Connect | Remove from Bicep |
| Custom HTML frontend (`app/static/`) | LibreChat UI | Keep as internal fallback only |
| `/sessions` REST endpoints | LibreChat conversations API | Remove |
| `X-Ms-Client-Principal-*` header extraction in `server.py` | LibreChat user model | Remove |

What does **not** change: all tool modules in `app/tools/`, the managed identity, ACR, Key Vault, and Container Apps Environment. The agent backend can remain as an internal-only developer tool.

---

## New Architecture

```
Browser
  │
  ▼
LibreChat Container App   (public ingress, port 3080)
  │      │         │
  │      │         └──► Cosmos DB for MongoDB API  (LibreChat history + users)
  │      │
  │      └──────────► Azure Cache for Redis  (rate limiting, session tokens)
  │
  └──► Azure OpenAI   (existing — model calls)
  └──► MCP Server Container App  (internal ingress — Azure tools)
            │
            └── Runs all existing app/tools/ modules via MCP SSE transport
                Same managed identity as the current agent container
```

The current agent Container App (`ca-azure-agent`) stays running at **internal ingress** — it remains useful as a developer/CLI interface but is no longer the primary user-facing surface.

---

## New Components

### 1. MCP Server

The existing `app/tools/` modules are already well-structured as standalone callable objects (`TOOL_REGISTRY`). Wrapping them as an MCP server requires one new file.

**New `app/mcp_server.py`:**
- Uses `mcp.server.fastmcp.FastMCP` (Anthropic's Python MCP SDK)
- Iterates over `TOOL_REGISTRY` and registers each tool as an MCP function
- Runs on port 8081, SSE transport (HTTP-based, compatible with Container Apps)
- Validates an `Authorization: Bearer <MCP_API_KEY>` header on every request (shared secret between LibreChat and the MCP server, stored in Key Vault)

The tool functions themselves are unchanged. Input schemas are already in the right shape for MCP.

**New requirement:** `mcp>=1.0.0`

**Dockerfile change:** expose port 8081; `CMD` runs both `uvicorn server:app --port 8080` and `python mcp_server.py --port 8081` via a process manager (e.g., `supervisord`) or a shell entrypoint script. Alternatively, build a second Docker image (`azure-agent-mcp`) from the same base and keep the two services separate — cleaner operationally.

**Haiku classifier note:** `agent.py` uses a Haiku pre-call to dynamically select which tool groups to send to the model. This is not needed in the LibreChat + MCP path — LibreChat advertises all registered MCP tools to Azure OpenAI and the model selects them naturally. The classifier stays in `agent.py` for the internal agent endpoint but plays no role in the LibreChat flow.

### 2. LibreChat Container App

- Image: `ghcr.io/danny-avila/librechat:latest` (or pin to a release tag for reproducibility)
- Port 3080, public ingress
- Configuration via environment variables + a `librechat.yaml` mounted from a Container Apps config volume or baked into a custom image layer

**New file: `librechat/librechat.yaml`** (checked into the repo)

```yaml
version: 1.1.7

endpoints:
  azureOpenAI:
    groups:
      - group: westus2
        apiKey: "${AZURE_OPENAI_API_KEY}"
        instanceName: "${AZURE_OPENAI_INSTANCE_NAME}"
        models:
          default: ["gpt-4.1"]
          fetch: false

mcp:
  servers:
    azure-tools:
      transport: sse
      url: "http://ca-azure-agent-mcp/sse"
      headers:
        Authorization: "Bearer ${MCP_API_KEY}"
```

**Key environment variables** (injected from Key Vault secrets via Container App secret references):

| Variable | Source |
|---|---|
| `MONGO_URI` | Cosmos DB connection string (Key Vault secret) |
| `REDIS_URI` | Redis connection string (Key Vault secret) |
| `JWT_SECRET` | Random 32-char string (Key Vault secret) |
| `CREDS_KEY` | 32-byte hex (Key Vault secret) |
| `CREDS_IV` | 16-byte hex (Key Vault secret) |
| `OPENID_CLIENT_ID` | Entra App Registration client ID (Key Vault secret) |
| `OPENID_CLIENT_SECRET` | Entra App Registration client secret (Key Vault secret) |
| `OPENID_ISSUER` | `https://login.microsoftonline.com/<tenant-id>/v2.0` |
| `OPENID_CALLBACK_URL` | `/oauth/openid/callback` |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI key (Key Vault secret) |
| `AZURE_OPENAI_INSTANCE_NAME` | Azure OpenAI resource name |
| `MCP_API_KEY` | Shared secret for MCP server auth (Key Vault secret) |
| `ALLOW_REGISTRATION` | `false` — all access via Entra OIDC only |
| `ALLOW_SOCIAL_LOGIN` | `true` |

### 3. Azure Cosmos DB for MongoDB API

- Serverless capacity mode (cost-effective for personal/low-traffic use)
- MongoDB API v7.0
- Database: `librechat`
- Managed identity **cannot** access Cosmos DB for MongoDB API via RBAC; uses connection string stored in Key Vault

**New Bicep module:** `infra/modules/cosmos-db.bicep`
- Outputs: connection string (stored directly in Key Vault as `cosmos-db-uri`)

### 4. Azure Cache for Redis

- SKU: Basic C0 (sufficient for LibreChat's rate limiting and session cache)
- TLS-only access
- Connection string stored in Key Vault as `redis-uri`

**New Bicep module:** `infra/modules/redis.bicep`

---

## Infrastructure Changes

### `infra/main.bicep` additions

```bicep
// New parameters
param entraClientId string
@secure() param entraClientSecret string
@secure() param libreChatJwtSecret string
@secure() param libreChatCredsKey string
@secure() param libreChatCredsIv string
@secure() param mcpApiKey string

// New modules
module cosmosDb   'modules/cosmos-db.bicep' = { ... }
module redis      'modules/redis.bicep'     = { ... }
module librechat  'modules/librechat-app.bicep' = { ... }
```

The Key Vault module gains additional `set_secret` calls for the new secrets. The `deployer` access policy already allows setting secrets, so no policy changes are needed.

### `infra/modules/container-apps.bicep` changes

- Add a second Container App `ca-azure-agent-mcp` (internal ingress, port 8081) alongside the existing `ca-azure-agent`
- Same managed identity as the current agent
- Change `ca-azure-agent` ingress from `external` to `internal` (it no longer needs to be public)

### Key Vault secrets added

| Secret name | Value |
|---|---|
| `cosmos-db-uri` | Cosmos DB connection string |
| `redis-uri` | Redis `rediss://` connection string |
| `librechat-jwt-secret` | Random secret |
| `librechat-creds-key` | 32-byte hex |
| `librechat-creds-iv` | 16-byte hex |
| `entra-client-secret` | Entra app client secret |
| `mcp-api-key` | Shared MCP auth secret |

### Entra App Registration changes

The registration from the previous auth plan needs one change:
- **Add** redirect URI: `https://<librechat-fqdn>/oauth/openid/callback`
- **Remove** (or keep for fallback): `https://<agent-fqdn>/.auth/login/aad/callback`

### GitHub Actions secrets added

| Secret | Purpose |
|---|---|
| `ENTRA_APP_CLIENT_ID` | LibreChat OIDC (same as previous plan) |
| `ENTRA_APP_CLIENT_SECRET` | LibreChat OIDC (same as previous plan) |
| `LIBRECHAT_JWT_SECRET` | Generated once, stored in GH secret |
| `LIBRECHAT_CREDS_KEY` | Generated once, stored in GH secret |
| `LIBRECHAT_CREDS_IV` | Generated once, stored in GH secret |
| `MCP_API_KEY` | Generated once, stored in GH secret |

---

## Authentication Flow

1. User navigates to LibreChat Container App URL
2. LibreChat login page shows "Sign in with Microsoft" (only social login enabled; password login disabled)
3. User authenticates with Entra ID — tenant MFA policy applies
4. Entra redirects to `/oauth/openid/callback`; LibreChat creates or updates the user record in Cosmos DB
5. Access control: enable "User Assignment Required" on the Entra app registration and assign users or groups — unauthorized users are rejected at the Entra consent page before reaching LibreChat
6. All subsequent requests are authenticated via LibreChat's own JWT session cookie

---

## What Previous Plan Artifacts Are Removed

- `session_store.py` — delete
- `GET /sessions`, `POST /sessions`, `DELETE /sessions/{session_id}` from `server.py` — delete
- OID/UPN header extraction from `websocket_endpoint` — delete
- `session_id` query param from WebSocket endpoint — delete
- Session sidebar from `app/static/index.html` — delete (LibreChat has its own)
- `infra/modules/storage.bicep` (Blob Storage for sessions) — delete
- `authConfigs` resource from `infra/modules/container-apps.bicep` — delete
- `azure-storage-blob` from `requirements.txt` — remove

---

## What Stays Unchanged

- All files in `app/tools/` — no changes
- `app/tools/__init__.py`, `TOOL_REGISTRY`, `GROUP_DESCRIPTIONS` — no changes
- `agent.py`, `server.py` (WebSocket path) — kept for internal developer use
- `infra/modules/identity.bicep`, `acr.bicep`, `keyvault.bicep` — no changes
- ACR build + Container Apps image update flow in `deploy.yml` — no changes

---

## Implementation Sequence

1. **`app/mcp_server.py`** — wrap `TOOL_REGISTRY` with `FastMCP`; SSE transport; API key auth
2. **`app/requirements.txt`** — add `mcp>=1.0.0`; remove `azure-storage-blob`
3. **Dockerfile** — expose 8081; add entrypoint script to run both servers (or create second image)
4. **`librechat/librechat.yaml`** — Azure OpenAI endpoint + MCP server config
5. **`infra/modules/cosmos-db.bicep`** — serverless Cosmos DB (MongoDB API)
6. **`infra/modules/redis.bicep`** — Azure Cache for Redis Basic C0
7. **`infra/modules/librechat-app.bicep`** — LibreChat Container App with KV secret references
8. **`infra/modules/container-apps.bicep`** — add MCP Container App; change agent to internal ingress; remove `authConfigs`
9. **`infra/main.bicep`** — wire in new modules and parameters; remove storage module
10. **`deploy.yml`** — add new secrets to the params JSON write step; update one-time setup notes
11. **Entra App Registration** — update redirect URI to LibreChat callback
12. **Remove previous plan artifacts** — `session_store.py`, `/sessions` endpoints, Storage account Bicep, session sidebar

---

## Cost Additions

| Resource | Tier | Estimated monthly cost |
|---|---|---|
| Azure Cache for Redis | Basic C0 | ~$16 |
| Cosmos DB (serverless) | — | ~$0.25/million RUs; near-zero for personal use |
| LibreChat Container App | Consumption | ~$0 at idle with min replicas = 0 |
| MCP Server Container App | Consumption | ~$0 at idle with min replicas = 0 |

The Redis instance is the only meaningful fixed cost. To eliminate it: run a `redis:7-alpine` container in the same Container Apps Environment (no SLA, fine for personal use; add a `ca-redis` Container App with internal ingress).
