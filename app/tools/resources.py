"""Tools for subscriptions and resource groups."""
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.subscription import SubscriptionClient
from config import credential
from tools.base import Tool


def _list_subscriptions() -> str:
    client = SubscriptionClient(credential)
    subs = list(client.subscriptions.list())
    if not subs:
        return "No subscriptions found."
    lines = [f"- {s.display_name} ({s.subscription_id})  state={s.state}" for s in subs]
    return "\n".join(lines)


def _list_resource_groups(subscription_id: str) -> str:
    client = ResourceManagementClient(credential, subscription_id)
    rgs = list(client.resource_groups.list())
    if not rgs:
        return f"No resource groups found in subscription {subscription_id}."
    lines = [f"- {rg.name}  location={rg.location}  state={rg.properties.provisioning_state}" for rg in rgs]
    return "\n".join(lines)


def _create_resource_group(subscription_id: str, resource_group: str, location: str) -> str:
    client = ResourceManagementClient(credential, subscription_id)
    rg = client.resource_groups.create_or_update(resource_group, {"location": location})
    return f"Resource group '{rg.name}' is {rg.properties.provisioning_state} in {rg.location}."


def _delete_resource_group(subscription_id: str, resource_group: str) -> str:
    client = ResourceManagementClient(credential, subscription_id)
    poller = client.resource_groups.begin_delete(resource_group)
    poller.result()
    return f"Resource group '{resource_group}' has been deleted."


def _list_resources(subscription_id: str, resource_group: str) -> str:
    client = ResourceManagementClient(credential, subscription_id)
    resources = list(client.resources.list_by_resource_group(resource_group))
    if not resources:
        return f"No resources found in resource group '{resource_group}'."
    lines = [f"- {r.name}  type={r.type}  location={r.location}" for r in resources]
    return "\n".join(lines)


TOOLS = [
    Tool(
        name="list_subscriptions",
        description="List all Azure subscriptions accessible with the current credentials.",
        input_schema={"type": "object", "properties": {}, "required": []},
        func=lambda: _list_subscriptions(),
    ),
    Tool(
        name="list_resource_groups",
        description="List all resource groups in an Azure subscription.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string", "description": "Azure subscription ID (GUID)."},
            },
            "required": ["subscription_id"],
        },
        func=_list_resource_groups,
    ),
    Tool(
        name="create_resource_group",
        description="Create a new resource group in an Azure subscription.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string", "description": "Azure subscription ID."},
                "resource_group": {"type": "string", "description": "Name for the new resource group."},
                "location": {"type": "string", "description": "Azure region, e.g. eastus, westeurope."},
            },
            "required": ["subscription_id", "resource_group", "location"],
        },
        func=_create_resource_group,
    ),
    Tool(
        name="delete_resource_group",
        description="Permanently delete a resource group and ALL resources inside it.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string", "description": "Name of the resource group to delete."},
            },
            "required": ["subscription_id", "resource_group"],
        },
        func=_delete_resource_group,
        destructive=True,
    ),
    Tool(
        name="list_resources",
        description="List all resources within a specific resource group.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group"],
        },
        func=_list_resources,
    ),
]
