# Session History and Authentication Plan

## Overview

Two related features to implement together:
- **Session history** — persist conversations across disconnects, page refreshes, and container restarts; allow switching between named sessions
- **Authentication** — require Entra ID login before accessing the tool; scope sessions per authenticated user

Neither feature is implemented yet. This document captures the design decisions so implementation can start without re-deriving the approach.

---

## Session History

### What's missing today

Each `AzureAgent` is created fresh per WebSocket connection (`server.py:33`) and holds `self.messages` in memory. A page refresh, WebSocket drop, or container restart loses the entire history. There is no way to return to a previous conversation.

### Storage backend — Azure Blob Storage

One JSON file per session stored in a new `sessions` blob container. Sessions are listed by blob prefix. No schema, no migrations, and blobs are easy to inspect manually.

Accessed via the Container App's managed identity — needs a new storage account added to `infra/` and a `Storage Blob Data Contributor` role grant on that account.

Once authentication is in place, blob paths are scoped per user: `{oid}/{session_id}.json`. This enforces isolation at the storage layer independently of any API-level checks. The Entra Object ID (OID) is used rather than UPN/email because it is immutable — it does not change if a user renames their account or changes their email.

### Session identity protocol

The browser passes a `session_id` UUID as a WebSocket query parameter (`/ws?session=<uuid>`). FastAPI's `WebSocket` object exposes query params directly.

The browser stores the current `session_id` in `localStorage`. On connect it reads the stored ID (or calls `crypto.randomUUID()` if none exists) and appends it to the WebSocket URL. Reconnects and page refreshes automatically restore the prior session without any extra handshake.

### Backend changes

**New `session_store.py` module:**
- `save_session(oid, session_id, messages, active_groups, display_name)` — serializes and writes to blob
- `load_session(oid, session_id)` → `(messages, active_groups)` — reads and deserializes
- `list_sessions(oid)` → list of `{id, name, created_at, updated_at, message_count}`
- `delete_session(oid, session_id)`

**Serialization note:** The Anthropic path stores SDK objects in `self.messages` (`response.content` is a list of typed `ContentBlock` objects). These must be converted to plain dicts before saving (they expose `.model_dump()`). Plain dicts can be loaded back as-is because the Anthropic API accepts both formats.

**`AzureAgent` changes:**
- Constructor accepts an optional `session_id` and `user_oid`; if provided, calls `load_session` to restore `messages` and `_active_groups`
- After each successful `chat()` turn, calls `save_session` with the updated state
- Display name is auto-generated from the first ~60 characters of the first user message

**`server.py` changes:**
- `websocket_endpoint` reads `session_id` from query param and `user_oid` from the `X-Ms-Client-Principal-Id` header; passes both to `AzureAgent`
- New REST endpoints:
  - `GET /sessions` — list sessions for the authenticated user
  - `POST /sessions` — create a new blank session, returns new UUID
  - `DELETE /sessions/{session_id}` — delete a session owned by the authenticated user

### Frontend changes

- On connect: read `localStorage.getItem('sessionId')` (or generate a new UUID), append as `?session=<id>` in the WebSocket URL
- Sessions sidebar: collapsible left panel listing past sessions by name and date, with a "New session" button at the top; clicking a session closes the current WebSocket, updates `localStorage`, and reconnects
- Display name shown in the header once the first message is sent; editable inline
- Existing "Reset conversation" button behaviour: decide whether reset clears the current session (same ID, wiped history) or starts a brand new session (new UUID)

---

## Authentication

### Approach — Container Apps EasyAuth

Azure Container Apps built-in authentication handles the entire OAuth2/OIDC flow at the infrastructure layer. No Python code changes are needed for authentication itself. EasyAuth intercepts all HTTP requests (including WebSocket upgrades) before they reach the app and injects the authenticated user's identity into request headers.

### Login flow

1. User navigates to the Container App URL
2. EasyAuth sees no valid session cookie, redirects to Microsoft login
3. User authenticates with their Entra ID credentials (tenant MFA policy applies automatically)
4. Entra redirects back, EasyAuth sets an encrypted session cookie
5. All subsequent requests — including the WebSocket upgrade — carry the cookie and are silently validated
6. The app receives:
   - `X-Ms-Client-Principal-Id` — the user's Entra Object ID (stable, unique)
   - `X-Ms-Client-Principal-Name` — the user's UPN / email

### Authorization — restricting who can log in

- **Tenant restriction** — only users in the configured Entra tenant can authenticate (default behaviour)
- **User/group assignment** — enable "User Assignment Required" on the app registration and add allowed users or groups; anyone not assigned gets a 403 at the Entra consent page before reaching the app

### Infrastructure changes

**Prerequisite — Entra ID App Registration** (one-time manual or scripted setup; Bicep cannot create Entra resources without Microsoft Graph permissions):
- Redirect URI: `https://<container-app-fqdn>/.auth/login/aad/callback`
- Client secret (rotatable), stored in the existing Key Vault as a new secret

**New Bicep resource — `Microsoft.App/containerApps/authConfigs`** child on the Container App:
- `unauthenticatedClientAction: RedirectToLoginPage`
- `identityProviders.azureActiveDirectory` configured with tenant ID, client ID, and the secret name
- `clientSecretSettingName` references a Container App secret backed by the Key Vault entry (same pattern as `ANTHROPIC_API_KEY`)

**New Bicep parameters:** `entraClientId` and `entraClientSecret` (`@secure()`), supplied by two new GitHub Actions secrets (`ENTRA_APP_CLIENT_ID`, `ENTRA_APP_CLIENT_SECRET`).

**New storage account** for session blobs (also needed by session history above) with `Storage Blob Data Contributor` granted to the Container App managed identity.

### Backend changes

Authentication requires no Python changes. Additions for consuming the identity:

- `server.py` WebSocket handler: extract OID and UPN from headers, pass to `AzureAgent` and session store
- `GET /sessions`: filtered by the calling user's OID
- `GET /`: optionally pass the user's name to the HTML template for display in the header

### Frontend changes

EasyAuth handles the login redirect transparently — no frontend auth code needed. Minor additions:

- Display the logged-in user's name/email in the header (read from `/.auth/me`, which EasyAuth exposes automatically)
- "Sign out" link that calls `/.auth/logout`

---

## Combined Implementation Sequence

1. **Infra** — add storage account to `infra/` (session blobs); add `authConfigs` resource (EasyAuth); add new Key Vault secrets and Bicep parameters; grant MI `Storage Blob Data Contributor`
2. **App registration** — one-time Entra setup (redirect URI, client secret, optionally user assignment); document as a setup prerequisite alongside the OIDC service principal steps in the workflow header
3. **`session_store.py`** — blob storage read/write/list/delete scoped by OID
4. **`AzureAgent`** — accept `session_id` and `user_oid`; load on init, save after each turn
5. **`server.py`** — extract OID/UPN from EasyAuth headers; pass through to sessions; new REST endpoints
6. **`index.html`** — localStorage session ID; sessions sidebar; WebSocket URL query param; user name in header; sign-out link
