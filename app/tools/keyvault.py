"""Tools for Azure Key Vault (management + secrets data plane)."""
from azure.mgmt.keyvault import KeyVaultManagementClient
from azure.keyvault.secrets import SecretClient
from config import credential
from tools.base import Tool


def _mgmt_client(subscription_id: str) -> KeyVaultManagementClient:
    return KeyVaultManagementClient(credential, subscription_id)


def _secret_client(vault_url: str) -> SecretClient:
    url = vault_url if vault_url.startswith("https://") else f"https://{vault_url}"
    return SecretClient(vault_url=url, credential=credential)


def _list_key_vaults(subscription_id: str, resource_group: str) -> str:
    vaults = list(_mgmt_client(subscription_id).vaults.list_by_resource_group(resource_group))
    if not vaults:
        return f"No key vaults found in '{resource_group}'."
    lines = [
        f"- {v.name}  vault_uri={v.properties.vault_uri}  location={v.location}  "
        f"sku={v.properties.sku.name}"
        for v in vaults
    ]
    return "\n".join(lines)


def _list_key_vault_secrets(vault_url: str) -> str:
    secrets = list(_secret_client(vault_url).list_properties_of_secrets())
    if not secrets:
        return f"No secrets found in vault '{vault_url}'."
    lines = []
    for s in secrets:
        enabled = s.enabled
        updated = str(s.updated_on)[:19] if s.updated_on else "n/a"
        lines.append(f"- {s.name}  enabled={enabled}  updated={updated}")
    return "\n".join(lines)


def _get_key_vault_secret(vault_url: str, secret_name: str) -> str:
    secret = _secret_client(vault_url).get_secret(secret_name)
    return (
        f"Name:    {secret.name}\n"
        f"Version: {secret.properties.version}\n"
        f"Enabled: {secret.properties.enabled}\n"
        f"Value:   {secret.value}"
    )


def _set_key_vault_secret(vault_url: str, secret_name: str, secret_value: str) -> str:
    secret = _secret_client(vault_url).set_secret(secret_name, secret_value)
    return f"Secret '{secret.name}' set in vault '{vault_url}' (version: {secret.properties.version})."


def _delete_key_vault_secret(vault_url: str, secret_name: str) -> str:
    poller = _secret_client(vault_url).begin_delete_secret(secret_name)
    poller.result()
    return (
        f"Secret '{secret_name}' has been soft-deleted from vault '{vault_url}'. "
        "It can be recovered during the soft-delete retention period."
    )


TOOLS = [
    Tool(
        name="list_key_vaults",
        description="List all Key Vaults in a resource group.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group"],
        },
        func=_list_key_vaults,
    ),
    Tool(
        name="list_key_vault_secrets",
        description="List the names of all secrets in a Key Vault. Does not reveal secret values.",
        input_schema={
            "type": "object",
            "properties": {
                "vault_url": {
                    "type": "string",
                    "description": "Key Vault URI, e.g. https://my-vault.vault.azure.net/",
                },
            },
            "required": ["vault_url"],
        },
        func=_list_key_vault_secrets,
    ),
    Tool(
        name="get_key_vault_secret",
        description="Retrieve the value of a secret from a Key Vault.",
        input_schema={
            "type": "object",
            "properties": {
                "vault_url": {"type": "string"},
                "secret_name": {"type": "string"},
            },
            "required": ["vault_url", "secret_name"],
        },
        func=_get_key_vault_secret,
    ),
    Tool(
        name="set_key_vault_secret",
        description="Create or update a secret in a Key Vault. Creates a new version if the secret already exists.",
        input_schema={
            "type": "object",
            "properties": {
                "vault_url": {"type": "string"},
                "secret_name": {"type": "string"},
                "secret_value": {"type": "string"},
            },
            "required": ["vault_url", "secret_name", "secret_value"],
        },
        func=_set_key_vault_secret,
        destructive=True,
    ),
    Tool(
        name="delete_key_vault_secret",
        description="Soft-delete a secret from a Key Vault. The secret can be recovered during the retention period.",
        input_schema={
            "type": "object",
            "properties": {
                "vault_url": {"type": "string"},
                "secret_name": {"type": "string"},
            },
            "required": ["vault_url", "secret_name"],
        },
        func=_delete_key_vault_secret,
        destructive=True,
    ),
]
