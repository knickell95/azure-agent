"""Read-only tools for Microsoft Entra ID (Azure AD) via Microsoft Graph REST API.

Authentication: uses the same DefaultAzureCredential as the rest of the agent,
but requests the Graph scope instead of the ARM scope.
"""
import requests
from config import credential
from tools.base import Tool

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_GRAPH_SCOPE = "https://graph.microsoft.com/.default"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _token() -> str:
    return credential.get_token(_GRAPH_SCOPE).token


def _headers() -> dict:
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


def _get(path: str, params: dict | None = None) -> dict:
    url = f"{_GRAPH_BASE}{path}"
    resp = requests.get(url, headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _list_all(path: str, params: dict | None = None, max_results: int = 100) -> list:
    """Follow @odata.nextLink pages up to max_results items."""
    results = []
    url = f"{_GRAPH_BASE}{path}"
    while url and len(results) < max_results:
        resp = requests.get(url, headers=_headers(), params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        results.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
        params = None  # nextLink already includes query params
    return results[:max_results]


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def _list_users(search: str | None = None, max_results: int = 50) -> str:
    params = {
        "$select": "displayName,userPrincipalName,id,accountEnabled,jobTitle,department,mail",
        "$top": min(max_results, 999),
    }
    if search:
        params["$search"] = f'"displayName:{search}" OR "userPrincipalName:{search}"'
        params["ConsistencyLevel"] = "eventual"

    try:
        users = _list_all("/users", params=params, max_results=max_results)
    except requests.HTTPError as exc:
        return f"[Graph error] {exc}"

    if not users:
        return "No users found."
    lines = [
        f"- {u.get('displayName', 'n/a')}  upn={u.get('userPrincipalName', 'n/a')}  "
        f"enabled={u.get('accountEnabled')}  dept={u.get('department', 'n/a')}  id={u.get('id')}"
        for u in users
    ]
    return "\n".join(lines)


def _get_user(user_id_or_upn: str) -> str:
    try:
        u = _get(f"/users/{user_id_or_upn}", params={
            "$select": "displayName,userPrincipalName,id,accountEnabled,jobTitle,department,mail,createdDateTime,signInActivity"
        })
    except requests.HTTPError as exc:
        return f"[Graph error] {exc}"

    last_sign_in = "n/a"
    if u.get("signInActivity"):
        last_sign_in = u["signInActivity"].get("lastSignInDateTime", "n/a")

    return (
        f"Display name:   {u.get('displayName')}\n"
        f"UPN:            {u.get('userPrincipalName')}\n"
        f"Object ID:      {u.get('id')}\n"
        f"Enabled:        {u.get('accountEnabled')}\n"
        f"Job title:      {u.get('jobTitle', 'n/a')}\n"
        f"Department:     {u.get('department', 'n/a')}\n"
        f"Mail:           {u.get('mail', 'n/a')}\n"
        f"Created:        {u.get('createdDateTime', 'n/a')}\n"
        f"Last sign-in:   {last_sign_in}"
    )


def _get_user_group_memberships(user_id_or_upn: str) -> str:
    try:
        groups = _list_all(f"/users/{user_id_or_upn}/memberOf", params={
            "$select": "displayName,id,groupTypes"
        })
    except requests.HTTPError as exc:
        return f"[Graph error] {exc}"

    if not groups:
        return f"User '{user_id_or_upn}' is not a member of any groups."
    lines = [
        f"- {g.get('displayName', 'n/a')}  id={g.get('id')}  "
        f"type={'Microsoft 365' if 'Unified' in g.get('groupTypes', []) else 'Security'}"
        for g in groups
    ]
    return "\n".join(lines)


def _get_user_assigned_roles(user_id_or_upn: str) -> str:
    try:
        roles = _list_all(f"/users/{user_id_or_upn}/transitiveMemberOf/microsoft.graph.directoryRole", params={
            "$select": "displayName,id,description"
        })
    except requests.HTTPError as exc:
        return f"[Graph error] {exc}"

    if not roles:
        return f"User '{user_id_or_upn}' has no Entra directory roles assigned."
    lines = [f"- {r.get('displayName')}  id={r.get('id')}" for r in roles]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

def _list_groups(search: str | None = None, max_results: int = 50) -> str:
    params = {
        "$select": "displayName,id,groupTypes,securityEnabled,mailEnabled,description,membershipRule",
        "$top": min(max_results, 999),
    }
    if search:
        params["$search"] = f'"displayName:{search}"'
        params["ConsistencyLevel"] = "eventual"

    try:
        groups = _list_all("/groups", params=params, max_results=max_results)
    except requests.HTTPError as exc:
        return f"[Graph error] {exc}"

    if not groups:
        return "No groups found."

    def _group_type(g: dict) -> str:
        types = g.get("groupTypes", [])
        if "Unified" in types:
            return "Microsoft 365"
        if g.get("securityEnabled") and "DynamicMembership" in types:
            return "Dynamic Security"
        if g.get("securityEnabled"):
            return "Security"
        return "Distribution"

    lines = [
        f"- {g.get('displayName', 'n/a')}  type={_group_type(g)}  id={g.get('id')}"
        for g in groups
    ]
    return "\n".join(lines)


def _get_group(group_id: str) -> str:
    try:
        g = _get(f"/groups/{group_id}", params={
            "$select": "displayName,id,description,groupTypes,securityEnabled,mailEnabled,membershipRule,createdDateTime"
        })
    except requests.HTTPError as exc:
        return f"[Graph error] {exc}"

    types = g.get("groupTypes", [])
    return (
        f"Display name:   {g.get('displayName')}\n"
        f"Object ID:      {g.get('id')}\n"
        f"Description:    {g.get('description', 'n/a')}\n"
        f"Type:           {'Microsoft 365' if 'Unified' in types else 'Security/Distribution'}\n"
        f"Dynamic:        {'Yes — rule: ' + g.get('membershipRule', '') if 'DynamicMembership' in types else 'No'}\n"
        f"Security:       {g.get('securityEnabled')}\n"
        f"Mail-enabled:   {g.get('mailEnabled')}\n"
        f"Created:        {g.get('createdDateTime', 'n/a')}"
    )


def _list_group_members(group_id: str) -> str:
    try:
        members = _list_all(f"/groups/{group_id}/members", params={
            "$select": "displayName,userPrincipalName,id,@odata.type"
        })
    except requests.HTTPError as exc:
        return f"[Graph error] {exc}"

    if not members:
        return f"Group '{group_id}' has no members."
    lines = [
        f"- {m.get('displayName', 'n/a')}  "
        f"upn={m.get('userPrincipalName', 'n/a')}  "
        f"type={m.get('@odata.type', '').split('.')[-1]}  id={m.get('id')}"
        for m in members
    ]
    return "\n".join(lines)


def _list_group_owners(group_id: str) -> str:
    try:
        owners = _list_all(f"/groups/{group_id}/owners", params={
            "$select": "displayName,userPrincipalName,id"
        })
    except requests.HTTPError as exc:
        return f"[Graph error] {exc}"

    if not owners:
        return f"Group '{group_id}' has no owners."
    lines = [
        f"- {o.get('displayName', 'n/a')}  upn={o.get('userPrincipalName', 'n/a')}  id={o.get('id')}"
        for o in owners
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# App Registrations
# ---------------------------------------------------------------------------

def _list_app_registrations(search: str | None = None, max_results: int = 50) -> str:
    params = {
        "$select": "displayName,appId,id,signInAudience,createdDateTime,passwordCredentials,keyCredentials",
        "$top": min(max_results, 999),
    }
    if search:
        params["$search"] = f'"displayName:{search}"'
        params["ConsistencyLevel"] = "eventual"

    try:
        apps = _list_all("/applications", params=params, max_results=max_results)
    except requests.HTTPError as exc:
        return f"[Graph error] {exc}"

    if not apps:
        return "No app registrations found."
    lines = []
    for a in apps:
        secrets_count = len(a.get("passwordCredentials", []))
        certs_count = len(a.get("keyCredentials", []))
        lines.append(
            f"- {a.get('displayName', 'n/a')}  appId={a.get('appId')}  "
            f"audience={a.get('signInAudience', 'n/a')}  "
            f"secrets={secrets_count}  certs={certs_count}  id={a.get('id')}"
        )
    return "\n".join(lines)


def _get_app_registration(app_id_or_object_id: str) -> str:
    """Accept either the appId (client ID) or the object ID."""
    try:
        # Try object ID first
        try:
            a = _get(f"/applications/{app_id_or_object_id}")
        except requests.HTTPError:
            # Fall back to filter by appId
            data = _get("/applications", params={
                "$filter": f"appId eq '{app_id_or_object_id}'",
                "$select": "displayName,appId,id,signInAudience,createdDateTime,passwordCredentials,keyCredentials,requiredResourceAccess,web,spa,publicClient",
            })
            items = data.get("value", [])
            if not items:
                return f"App registration '{app_id_or_object_id}' not found."
            a = items[0]
    except requests.HTTPError as exc:
        return f"[Graph error] {exc}"

    secrets = a.get("passwordCredentials", [])
    certs = a.get("keyCredentials", [])
    secret_lines = "\n".join(
        f"  - {s.get('displayName', 'n/a')}  expires={s.get('endDateTime', 'n/a')}"
        for s in secrets
    ) or "  (none)"
    cert_lines = "\n".join(
        f"  - {c.get('displayName', 'n/a')}  expires={c.get('endDateTime', 'n/a')}"
        for c in certs
    ) or "  (none)"

    redirect_uris = (
        (a.get("web") or {}).get("redirectUris", [])
        + (a.get("spa") or {}).get("redirectUris", [])
        + (a.get("publicClient") or {}).get("redirectUris", [])
    )

    return (
        f"Display name:    {a.get('displayName')}\n"
        f"App (client) ID: {a.get('appId')}\n"
        f"Object ID:       {a.get('id')}\n"
        f"Sign-in audience:{a.get('signInAudience', 'n/a')}\n"
        f"Created:         {a.get('createdDateTime', 'n/a')}\n"
        f"Redirect URIs:   {', '.join(redirect_uris) or 'none'}\n"
        f"Client secrets ({len(secrets)}):\n{secret_lines}\n"
        f"Certificates ({len(certs)}):\n{cert_lines}"
    )


def _list_app_permissions(app_id_or_object_id: str) -> str:
    """List the API permissions requested by an app registration."""
    try:
        try:
            a = _get(f"/applications/{app_id_or_object_id}", params={
                "$select": "displayName,requiredResourceAccess"
            })
        except requests.HTTPError:
            data = _get("/applications", params={
                "$filter": f"appId eq '{app_id_or_object_id}'",
                "$select": "displayName,requiredResourceAccess",
            })
            items = data.get("value", [])
            if not items:
                return f"App registration '{app_id_or_object_id}' not found."
            a = items[0]
    except requests.HTTPError as exc:
        return f"[Graph error] {exc}"

    accesses = a.get("requiredResourceAccess", [])
    if not accesses:
        return f"App '{a.get('displayName')}' has no API permissions configured."

    lines = [f"App: {a.get('displayName')}"]
    for resource in accesses:
        resource_app_id = resource.get("resourceAppId")
        lines.append(f"\n  Resource: {resource_app_id}")
        for perm in resource.get("resourceAccess", []):
            perm_type = "Role (application)" if perm.get("type") == "Role" else "Scope (delegated)"
            lines.append(f"    - {perm_type}  id={perm.get('id')}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Service Principals
# ---------------------------------------------------------------------------

def _list_service_principals(search: str | None = None, max_results: int = 50) -> str:
    params = {
        "$select": "displayName,appId,id,servicePrincipalType,accountEnabled,appOwnerOrganizationId",
        "$top": min(max_results, 999),
    }
    if search:
        params["$search"] = f'"displayName:{search}"'
        params["ConsistencyLevel"] = "eventual"

    try:
        sps = _list_all("/servicePrincipals", params=params, max_results=max_results)
    except requests.HTTPError as exc:
        return f"[Graph error] {exc}"

    if not sps:
        return "No service principals found."
    lines = [
        f"- {sp.get('displayName', 'n/a')}  type={sp.get('servicePrincipalType', 'n/a')}  "
        f"appId={sp.get('appId')}  enabled={sp.get('accountEnabled')}  id={sp.get('id')}"
        for sp in sps
    ]
    return "\n".join(lines)


def _get_service_principal(sp_id: str) -> str:
    try:
        sp = _get(f"/servicePrincipals/{sp_id}", params={
            "$select": "displayName,appId,id,servicePrincipalType,accountEnabled,appOwnerOrganizationId,replyUrls,tags"
        })
    except requests.HTTPError as exc:
        return f"[Graph error] {exc}"

    return (
        f"Display name:    {sp.get('displayName')}\n"
        f"App (client) ID: {sp.get('appId')}\n"
        f"Object ID:       {sp.get('id')}\n"
        f"Type:            {sp.get('servicePrincipalType', 'n/a')}\n"
        f"Enabled:         {sp.get('accountEnabled')}\n"
        f"Owner tenant:    {sp.get('appOwnerOrganizationId', 'n/a')}\n"
        f"Tags:            {', '.join(sp.get('tags', [])) or 'none'}"
    )


def _list_sp_app_role_assignments(sp_id: str) -> str:
    """List app role assignments (application permissions) granted to a service principal."""
    try:
        assignments = _list_all(f"/servicePrincipals/{sp_id}/appRoleAssignments", params={
            "$select": "principalDisplayName,resourceDisplayName,appRoleId,createdDateTime"
        })
    except requests.HTTPError as exc:
        return f"[Graph error] {exc}"

    if not assignments:
        return f"No app role assignments found for service principal '{sp_id}'."
    lines = [
        f"- resource={a.get('resourceDisplayName', 'n/a')}  "
        f"roleId={a.get('appRoleId')}  granted={a.get('createdDateTime', 'n/a')[:10]}"
        for a in assignments
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------

def _list_devices(search: str | None = None, max_results: int = 50) -> str:
    params = {
        "$select": "displayName,id,operatingSystem,operatingSystemVersion,isCompliant,isManaged,trustType,approximateLastSignInDateTime",
        "$top": min(max_results, 999),
    }
    if search:
        params["$search"] = f'"displayName:{search}"'
        params["ConsistencyLevel"] = "eventual"

    try:
        devices = _list_all("/devices", params=params, max_results=max_results)
    except requests.HTTPError as exc:
        return f"[Graph error] {exc}"

    if not devices:
        return "No devices found."
    lines = [
        f"- {d.get('displayName', 'n/a')}  os={d.get('operatingSystem', 'n/a')} {d.get('operatingSystemVersion', '')}  "
        f"compliant={d.get('isCompliant')}  managed={d.get('isManaged')}  "
        f"trust={d.get('trustType', 'n/a')}  last_seen={str(d.get('approximateLastSignInDateTime', 'n/a'))[:10]}"
        for d in devices
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Directory Roles
# ---------------------------------------------------------------------------

def _list_directory_roles() -> str:
    try:
        roles = _list_all("/directoryRoles", params={"$select": "displayName,id,description"})
    except requests.HTTPError as exc:
        return f"[Graph error] {exc}"

    if not roles:
        return "No active directory roles found."
    lines = [f"- {r.get('displayName', 'n/a')}  id={r.get('id')}" for r in roles]
    return "\n".join(lines)


def _list_directory_role_members(role_id: str) -> str:
    try:
        members = _list_all(f"/directoryRoles/{role_id}/members", params={
            "$select": "displayName,userPrincipalName,id"
        })
    except requests.HTTPError as exc:
        return f"[Graph error] {exc}"

    if not members:
        return f"No members in directory role '{role_id}'."
    lines = [
        f"- {m.get('displayName', 'n/a')}  upn={m.get('userPrincipalName', 'n/a')}  id={m.get('id')}"
        for m in members
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS = [
    # -- Users --
    Tool(
        name="list_entra_users",
        description=(
            "List Entra ID users. Optionally filter by display name or UPN with the search parameter. "
            "Returns up to max_results users (default 50)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "search": {"type": "string", "description": "Optional name or UPN search term."},
                "max_results": {"type": "integer", "default": 50},
            },
            "required": [],
        },
        func=_list_users,
    ),
    Tool(
        name="get_entra_user",
        description="Get detailed information about a specific Entra ID user by object ID or UPN.",
        input_schema={
            "type": "object",
            "properties": {
                "user_id_or_upn": {"type": "string", "description": "Object ID (GUID) or userPrincipalName."},
            },
            "required": ["user_id_or_upn"],
        },
        func=_get_user,
    ),
    Tool(
        name="get_entra_user_groups",
        description="List all groups a specific Entra ID user is a member of.",
        input_schema={
            "type": "object",
            "properties": {
                "user_id_or_upn": {"type": "string"},
            },
            "required": ["user_id_or_upn"],
        },
        func=_get_user_group_memberships,
    ),
    Tool(
        name="get_entra_user_roles",
        description="List Entra directory roles assigned to a specific user.",
        input_schema={
            "type": "object",
            "properties": {
                "user_id_or_upn": {"type": "string"},
            },
            "required": ["user_id_or_upn"],
        },
        func=_get_user_assigned_roles,
    ),
    # -- Groups --
    Tool(
        name="list_entra_groups",
        description="List Entra ID groups. Optionally filter by display name with the search parameter.",
        input_schema={
            "type": "object",
            "properties": {
                "search": {"type": "string", "description": "Optional display name search term."},
                "max_results": {"type": "integer", "default": 50},
            },
            "required": [],
        },
        func=_list_groups,
    ),
    Tool(
        name="get_entra_group",
        description="Get detailed information about a specific Entra ID group by object ID.",
        input_schema={
            "type": "object",
            "properties": {
                "group_id": {"type": "string", "description": "Group object ID (GUID)."},
            },
            "required": ["group_id"],
        },
        func=_get_group,
    ),
    Tool(
        name="list_entra_group_members",
        description="List all members of an Entra ID group.",
        input_schema={
            "type": "object",
            "properties": {
                "group_id": {"type": "string"},
            },
            "required": ["group_id"],
        },
        func=_list_group_members,
    ),
    Tool(
        name="list_entra_group_owners",
        description="List the owners of an Entra ID group.",
        input_schema={
            "type": "object",
            "properties": {
                "group_id": {"type": "string"},
            },
            "required": ["group_id"],
        },
        func=_list_group_owners,
    ),
    # -- App Registrations --
    Tool(
        name="list_entra_app_registrations",
        description="List Entra ID app registrations, including secret and certificate counts.",
        input_schema={
            "type": "object",
            "properties": {
                "search": {"type": "string", "description": "Optional display name search term."},
                "max_results": {"type": "integer", "default": 50},
            },
            "required": [],
        },
        func=_list_app_registrations,
    ),
    Tool(
        name="get_entra_app_registration",
        description=(
            "Get detailed information about an app registration including redirect URIs, "
            "client secrets, and certificates. Accepts either the appId (client ID) or object ID."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "app_id_or_object_id": {"type": "string", "description": "App (client) ID or object ID."},
            },
            "required": ["app_id_or_object_id"],
        },
        func=_get_app_registration,
    ),
    Tool(
        name="list_entra_app_permissions",
        description="List the API permissions configured for an app registration.",
        input_schema={
            "type": "object",
            "properties": {
                "app_id_or_object_id": {"type": "string"},
            },
            "required": ["app_id_or_object_id"],
        },
        func=_list_app_permissions,
    ),
    # -- Service Principals --
    Tool(
        name="list_entra_service_principals",
        description="List Entra ID service principals (enterprise applications). Optionally filter by name.",
        input_schema={
            "type": "object",
            "properties": {
                "search": {"type": "string", "description": "Optional display name search term."},
                "max_results": {"type": "integer", "default": 50},
            },
            "required": [],
        },
        func=_list_service_principals,
    ),
    Tool(
        name="get_entra_service_principal",
        description="Get detailed information about a specific service principal by object ID.",
        input_schema={
            "type": "object",
            "properties": {
                "sp_id": {"type": "string", "description": "Service principal object ID (GUID)."},
            },
            "required": ["sp_id"],
        },
        func=_get_service_principal,
    ),
    Tool(
        name="list_entra_sp_app_role_assignments",
        description="List the application permissions (app roles) granted to a service principal.",
        input_schema={
            "type": "object",
            "properties": {
                "sp_id": {"type": "string"},
            },
            "required": ["sp_id"],
        },
        func=_list_sp_app_role_assignments,
    ),
    # -- Devices --
    Tool(
        name="list_entra_devices",
        description="List Entra ID registered/joined devices including compliance and management state.",
        input_schema={
            "type": "object",
            "properties": {
                "search": {"type": "string", "description": "Optional device name search term."},
                "max_results": {"type": "integer", "default": 50},
            },
            "required": [],
        },
        func=_list_devices,
    ),
    # -- Directory Roles --
    Tool(
        name="list_entra_directory_roles",
        description="List all active Entra ID directory roles (e.g. Global Administrator, User Administrator).",
        input_schema={
            "type": "object",
            "properties": {},
            "required": [],
        },
        func=lambda: _list_directory_roles(),
    ),
    Tool(
        name="list_entra_directory_role_members",
        description="List all members assigned to a specific Entra ID directory role.",
        input_schema={
            "type": "object",
            "properties": {
                "role_id": {"type": "string", "description": "Directory role object ID."},
            },
            "required": ["role_id"],
        },
        func=_list_directory_role_members,
    ),
]
