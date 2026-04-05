"""Tools for Azure User-Assigned Managed Identities."""
from azure.mgmt.msi import ManagedServiceIdentityClient
from config import credential
from tools.base import Tool


def _client(subscription_id: str) -> ManagedServiceIdentityClient:
    return ManagedServiceIdentityClient(credential, subscription_id)


def _list_user_assigned_identities(subscription_id: str, resource_group: str) -> str:
    identities = list(_client(subscription_id).user_assigned_identities.list_by_resource_group(resource_group))
    if not identities:
        return f"No user-assigned managed identities found in '{resource_group}'."
    lines = []
    for i in identities:
        lines.append(
            f"- {i.name}  location={i.location}  "
            f"client_id={i.client_id}  principal_id={i.principal_id}"
        )
    return "\n".join(lines)


def _get_user_assigned_identity(
    subscription_id: str,
    resource_group: str,
    identity_name: str,
) -> str:
    i = _client(subscription_id).user_assigned_identities.get(resource_group, identity_name)
    return (
        f"Name:         {i.name}\n"
        f"Resource ID:  {i.id}\n"
        f"Location:     {i.location}\n"
        f"Client ID:    {i.client_id}\n"
        f"Principal ID: {i.principal_id}\n"
        f"Tenant ID:    {i.tenant_id}"
    )


def _create_user_assigned_identity(
    subscription_id: str,
    resource_group: str,
    identity_name: str,
    location: str,
) -> str:
    i = _client(subscription_id).user_assigned_identities.create_or_update(
        resource_group,
        identity_name,
        {"location": location},
    )
    return (
        f"User-assigned managed identity '{i.name}' created.\n"
        f"  Resource ID:  {i.id}\n"
        f"  Client ID:    {i.client_id}\n"
        f"  Principal ID: {i.principal_id}\n"
        f"  Location:     {i.location}"
    )


def _update_user_assigned_identity_tags(
    subscription_id: str,
    resource_group: str,
    identity_name: str,
    tags_json: str,
) -> str:
    import json
    try:
        tags = json.loads(tags_json)
    except json.JSONDecodeError as exc:
        return f"Invalid JSON in tags: {exc}"

    i = _client(subscription_id).user_assigned_identities.update(
        resource_group,
        identity_name,
        {"tags": tags},
    )
    tag_str = ", ".join(f"{k}={v}" for k, v in (i.tags or {}).items()) or "(none)"
    return f"Identity '{i.name}' updated. Tags: {tag_str}"


def _delete_user_assigned_identity(
    subscription_id: str,
    resource_group: str,
    identity_name: str,
) -> str:
    _client(subscription_id).user_assigned_identities.delete(resource_group, identity_name)
    return f"User-assigned managed identity '{identity_name}' has been deleted."


def _list_associated_resources(
    subscription_id: str,
    resource_group: str,
    identity_name: str,
) -> str:
    resources = list(
        _client(subscription_id).user_assigned_identities.list_associated_resources(
            resource_group, identity_name
        )
    )
    if not resources:
        return f"No resources are currently using identity '{identity_name}'."
    lines = []
    for r in resources:
        lines.append(f"- {r.name}  type={r.resource_type}  group={r.resource_group_name}")
    return "\n".join(lines)


TOOLS = [
    Tool(
        name="list_user_assigned_identities",
        description="List all user-assigned managed identities in a resource group.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group"],
        },
        func=_list_user_assigned_identities,
    ),
    Tool(
        name="get_user_assigned_identity",
        description=(
            "Get full details of a user-assigned managed identity, including its "
            "resource ID, client ID, and principal ID. The principal ID is needed to "
            "grant the identity Azure RBAC roles via create_role_assignment."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "identity_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "identity_name"],
        },
        func=_get_user_assigned_identity,
    ),
    Tool(
        name="create_user_assigned_identity",
        description=(
            "Create a new user-assigned managed identity. Returns the resource ID, "
            "client ID, and principal ID. Use create_role_assignment with the principal ID "
            "to grant this identity permissions on Azure resources."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "identity_name": {"type": "string"},
                "location": {"type": "string", "description": "Azure region, e.g. eastus."},
            },
            "required": ["subscription_id", "resource_group", "identity_name", "location"],
        },
        func=_create_user_assigned_identity,
    ),
    Tool(
        name="update_user_assigned_identity_tags",
        description="Update the tags on a user-assigned managed identity.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "identity_name": {"type": "string"},
                "tags_json": {
                    "type": "string",
                    "description": 'JSON object of tag key-value pairs, e.g. {"env":"prod","team":"platform"}.',
                },
            },
            "required": ["subscription_id", "resource_group", "identity_name", "tags_json"],
        },
        func=_update_user_assigned_identity_tags,
    ),
    Tool(
        name="delete_user_assigned_identity",
        description="Permanently delete a user-assigned managed identity.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "identity_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "identity_name"],
        },
        func=_delete_user_assigned_identity,
        destructive=True,
    ),
    Tool(
        name="list_identity_associated_resources",
        description=(
            "List all Azure resources that are currently using a user-assigned managed identity. "
            "Useful before deleting an identity to check what would lose access."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "identity_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "identity_name"],
        },
        func=_list_associated_resources,
    ),
]
