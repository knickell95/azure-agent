"""Tools for storage accounts and blob containers."""
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.storage.models import StorageAccountCreateParameters, Sku, Kind
from config import credential
from tools.base import Tool


def _client(subscription_id: str) -> StorageManagementClient:
    return StorageManagementClient(credential, subscription_id)


def _list_storage_accounts(subscription_id: str, resource_group: str) -> str:
    accounts = list(_client(subscription_id).storage_accounts.list_by_resource_group(resource_group))
    if not accounts:
        return f"No storage accounts found in '{resource_group}'."
    lines = [
        f"- {a.name}  kind={a.kind}  sku={a.sku.name}  location={a.location}  "
        f"access_tier={a.access_tier}"
        for a in accounts
    ]
    return "\n".join(lines)


def _create_storage_account(
    subscription_id: str,
    resource_group: str,
    account_name: str,
    location: str,
    sku_name: str = "Standard_LRS",
    kind: str = "StorageV2",
) -> str:
    poller = _client(subscription_id).storage_accounts.begin_create(
        resource_group,
        account_name,
        StorageAccountCreateParameters(
            sku=Sku(name=sku_name),
            kind=Kind(kind),
            location=location,
        ),
    )
    account = poller.result()
    return f"Storage account '{account.name}' created ({account.sku.name}, {account.kind}) in {account.location}."


def _delete_storage_account(subscription_id: str, resource_group: str, account_name: str) -> str:
    _client(subscription_id).storage_accounts.delete(resource_group, account_name)
    return f"Storage account '{account_name}' has been deleted."


def _list_blob_containers(subscription_id: str, resource_group: str, account_name: str) -> str:
    containers = list(_client(subscription_id).blob_containers.list(resource_group, account_name))
    if not containers:
        return f"No blob containers found in storage account '{account_name}'."
    lines = [f"- {c.name}  public_access={c.public_access}" for c in containers]
    return "\n".join(lines)


TOOLS = [
    Tool(
        name="list_storage_accounts",
        description="List all storage accounts in a resource group.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group"],
        },
        func=_list_storage_accounts,
    ),
    Tool(
        name="create_storage_account",
        description="Create a new Azure storage account.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "account_name": {"type": "string", "description": "Globally unique, 3-24 lowercase alphanumeric chars."},
                "location": {"type": "string"},
                "sku_name": {
                    "type": "string",
                    "description": "Replication type.",
                    "enum": ["Standard_LRS", "Standard_GRS", "Standard_RAGRS", "Standard_ZRS", "Premium_LRS"],
                    "default": "Standard_LRS",
                },
                "kind": {
                    "type": "string",
                    "enum": ["StorageV2", "BlobStorage", "FileStorage"],
                    "default": "StorageV2",
                },
            },
            "required": ["subscription_id", "resource_group", "account_name", "location"],
        },
        func=_create_storage_account,
    ),
    Tool(
        name="delete_storage_account",
        description="Permanently delete a storage account and all its data.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "account_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "account_name"],
        },
        func=_delete_storage_account,
        destructive=True,
    ),
    Tool(
        name="list_blob_containers",
        description="List blob containers within a storage account.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "account_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "account_name"],
        },
        func=_list_blob_containers,
    ),
]
