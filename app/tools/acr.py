"""Tools for Azure Container Registry (ACR)."""
from azure.mgmt.containerregistry import ContainerRegistryManagementClient
from azure.containerregistry import ContainerRegistryClient
from config import credential
from tools.base import Tool


def _mgmt_client(subscription_id: str) -> ContainerRegistryManagementClient:
    return ContainerRegistryManagementClient(credential, subscription_id)


def _data_client(login_server: str) -> ContainerRegistryClient:
    return ContainerRegistryClient(f"https://{login_server}", credential)


def _list_container_registries(subscription_id: str, resource_group: str) -> str:
    registries = list(_mgmt_client(subscription_id).registries.list_by_resource_group(resource_group))
    if not registries:
        return f"No container registries found in '{resource_group}'."
    lines = [
        f"- {r.name}  login_server={r.login_server}  sku={r.sku.name}  "
        f"location={r.location}  provisioning={r.provisioning_state}"
        for r in registries
    ]
    return "\n".join(lines)


def _list_acr_repositories(subscription_id: str, resource_group: str, registry_name: str) -> str:
    reg = _mgmt_client(subscription_id).registries.get(resource_group, registry_name)
    repos = list(_data_client(reg.login_server).list_repository_names())
    if not repos:
        return f"No repositories found in registry '{registry_name}'."
    return "\n".join(f"- {r}" for r in repos)


def _list_acr_tags(
    subscription_id: str, resource_group: str, registry_name: str, repository: str
) -> str:
    reg = _mgmt_client(subscription_id).registries.get(resource_group, registry_name)
    tags = list(_data_client(reg.login_server).list_tag_properties(repository))
    if not tags:
        return f"No tags found for repository '{repository}' in '{registry_name}'."
    lines = []
    for t in sorted(tags, key=lambda x: x.last_updated_on or x.created_on, reverse=True):
        updated = str(t.last_updated_on)[:19] if t.last_updated_on else "n/a"
        lines.append(f"- {t.name}  updated={updated}  digest={t.digest[:19]}...")
    return "\n".join(lines)


def _delete_acr_tag(
    subscription_id: str, resource_group: str, registry_name: str, repository: str, tag: str
) -> str:
    reg = _mgmt_client(subscription_id).registries.get(resource_group, registry_name)
    _data_client(reg.login_server).delete_tag(repository, tag)
    return f"Tag '{tag}' deleted from '{registry_name}/{repository}'."


TOOLS = [
    Tool(
        name="list_container_registries",
        description="List all Azure Container Registries (ACR) in a resource group.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group"],
        },
        func=_list_container_registries,
    ),
    Tool(
        name="list_acr_repositories",
        description="List all image repositories in an Azure Container Registry.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "registry_name": {"type": "string", "description": "The ACR name (not the login server)."},
            },
            "required": ["subscription_id", "resource_group", "registry_name"],
        },
        func=_list_acr_repositories,
    ),
    Tool(
        name="list_acr_tags",
        description="List all tags for a repository in an Azure Container Registry, newest first.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "registry_name": {"type": "string"},
                "repository": {"type": "string", "description": "Repository name, e.g. 'azure-agent'."},
            },
            "required": ["subscription_id", "resource_group", "registry_name", "repository"],
        },
        func=_list_acr_tags,
    ),
    Tool(
        name="delete_acr_tag",
        description="Delete a specific image tag from an ACR repository. The underlying manifest is only removed if no other tags reference it.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "registry_name": {"type": "string"},
                "repository": {"type": "string"},
                "tag": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "registry_name", "repository", "tag"],
        },
        func=_delete_acr_tag,
        destructive=True,
    ),
]
