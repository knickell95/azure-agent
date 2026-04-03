"""Tools for RBAC role assignments and service principals."""
from azure.mgmt.authorization import AuthorizationManagementClient
from config import credential
from tools.base import Tool


def _client(subscription_id: str) -> AuthorizationManagementClient:
    return AuthorizationManagementClient(credential, subscription_id)


def _list_role_assignments(subscription_id: str, resource_group: str | None = None) -> str:
    c = _client(subscription_id)
    scope = (
        f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
        if resource_group
        else f"/subscriptions/{subscription_id}"
    )
    assignments = list(c.role_assignments.list_for_scope(scope))
    if not assignments:
        return f"No role assignments found at scope '{scope}'."
    lines = [
        f"- principal={a.principal_id}  role={a.role_definition_id.split('/')[-1]}  scope={a.scope}"
        for a in assignments
    ]
    return "\n".join(lines)


def _list_role_definitions(subscription_id: str) -> str:
    c = _client(subscription_id)
    scope = f"/subscriptions/{subscription_id}"
    defs = list(c.role_definitions.list(scope))
    built_in = [d for d in defs if d.role_type == "BuiltInRole"]
    lines = [f"- {d.role_name}  id={d.name}" for d in sorted(built_in, key=lambda x: x.role_name or "")]
    return "\n".join(lines)


def _create_role_assignment(
    subscription_id: str,
    principal_id: str,
    role_definition_id: str,
    scope: str,
) -> str:
    import uuid
    c = _client(subscription_id)
    assignment_name = str(uuid.uuid4())
    assignment = c.role_assignments.create(
        scope,
        assignment_name,
        {
            "role_definition_id": role_definition_id,
            "principal_id": principal_id,
        },
    )
    return (
        f"Role assignment created.\n"
        f"  Principal: {assignment.principal_id}\n"
        f"  Role: {assignment.role_definition_id.split('/')[-1]}\n"
        f"  Scope: {assignment.scope}"
    )


def _delete_role_assignment(subscription_id: str, scope: str, assignment_name: str) -> str:
    _client(subscription_id).role_assignments.delete(scope, assignment_name)
    return f"Role assignment '{assignment_name}' at scope '{scope}' has been deleted."


TOOLS = [
    Tool(
        name="list_role_assignments",
        description=(
            "List RBAC role assignments at a subscription or resource group scope. "
            "Leave resource_group empty to list at the subscription level."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string", "description": "Optional. Omit to list at subscription scope."},
            },
            "required": ["subscription_id"],
        },
        func=_list_role_assignments,
    ),
    Tool(
        name="list_role_definitions",
        description="List all built-in Azure role definitions available in a subscription.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
            },
            "required": ["subscription_id"],
        },
        func=_list_role_definitions,
    ),
    Tool(
        name="create_role_assignment",
        description="Assign an Azure RBAC role to a principal at a given scope.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "principal_id": {"type": "string", "description": "Object ID of the user, group, or service principal."},
                "role_definition_id": {"type": "string", "description": "Full resource ID of the role definition."},
                "scope": {"type": "string", "description": "ARM scope, e.g. /subscriptions/{id}/resourceGroups/{rg}."},
            },
            "required": ["subscription_id", "principal_id", "role_definition_id", "scope"],
        },
        func=_create_role_assignment,
    ),
    Tool(
        name="delete_role_assignment",
        description="Remove an RBAC role assignment.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "scope": {"type": "string"},
                "assignment_name": {"type": "string", "description": "GUID name of the role assignment."},
            },
            "required": ["subscription_id", "scope", "assignment_name"],
        },
        func=_delete_role_assignment,
        destructive=True,
    ),
]
