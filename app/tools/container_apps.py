"""Tools for Azure Container Apps and Container App Environments."""
from azure.mgmt.appcontainers import ContainerAppsAPIClient
from config import credential
from tools.base import Tool


def _client(subscription_id: str) -> ContainerAppsAPIClient:
    return ContainerAppsAPIClient(credential, subscription_id)


def _list_container_apps(subscription_id: str, resource_group: str) -> str:
    apps = list(_client(subscription_id).container_apps.list_by_resource_group(resource_group))
    if not apps:
        return f"No container apps found in '{resource_group}'."
    lines = []
    for a in apps:
        fqdn = ""
        if a.configuration and a.configuration.ingress and a.configuration.ingress.fqdn:
            fqdn = f"  url=https://{a.configuration.ingress.fqdn}"
        lines.append(
            f"- {a.name}  location={a.location}  "
            f"provisioning={a.provisioning_state}{fqdn}"
        )
    return "\n".join(lines)


def _get_container_app(subscription_id: str, resource_group: str, app_name: str) -> str:
    a = _client(subscription_id).container_apps.get(resource_group, app_name)
    ing = a.configuration.ingress if a.configuration else None
    url = f"https://{ing.fqdn}" if ing and ing.fqdn else "no external ingress"
    images = "unknown"
    min_r = max_r = "n/a"
    if a.template:
        if a.template.containers:
            images = ", ".join(c.image or "?" for c in a.template.containers)
        if a.template.scale:
            min_r = a.template.scale.min_replicas
            max_r = a.template.scale.max_replicas
    return (
        f"Name:              {a.name}\n"
        f"Location:          {a.location}\n"
        f"Provisioning:      {a.provisioning_state}\n"
        f"Latest revision:   {a.latest_revision_name}\n"
        f"Image(s):          {images}\n"
        f"URL:               {url}\n"
        f"Scale:             min={min_r}  max={max_r}"
    )


def _list_container_app_revisions(subscription_id: str, resource_group: str, app_name: str) -> str:
    revisions = list(
        _client(subscription_id).container_app_revisions.list_revisions(resource_group, app_name)
    )
    if not revisions:
        return f"No revisions found for '{app_name}'."
    lines = []
    for r in revisions:
        created = str(r.created_time)[:19] if r.created_time else "n/a"
        lines.append(
            f"- {r.name}  active={r.active}  state={r.running_state}  "
            f"replicas={r.replicas}  health={r.health_state}  created={created}"
        )
    return "\n".join(lines)


def _restart_container_app_revision(
    subscription_id: str, resource_group: str, app_name: str, revision_name: str
) -> str:
    _client(subscription_id).container_app_revisions.restart_revision(
        resource_group, app_name, revision_name
    )
    return f"Revision '{revision_name}' of container app '{app_name}' has been restarted."


def _list_managed_environments(subscription_id: str, resource_group: str) -> str:
    envs = list(
        _client(subscription_id).managed_environments.list_by_resource_group(resource_group)
    )
    if not envs:
        return f"No Container App Environments found in '{resource_group}'."
    lines = [
        f"- {e.name}  location={e.location}  provisioning={e.provisioning_state}"
        for e in envs
    ]
    return "\n".join(lines)


TOOLS = [
    Tool(
        name="list_container_apps",
        description="List all Container Apps in a resource group.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group"],
        },
        func=_list_container_apps,
    ),
    Tool(
        name="get_container_app",
        description="Get details of a Container App: image, URL, latest revision, and scale settings.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "app_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "app_name"],
        },
        func=_get_container_app,
    ),
    Tool(
        name="list_container_app_revisions",
        description="List all revisions of a Container App with their running state, replica count, and health.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "app_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "app_name"],
        },
        func=_list_container_app_revisions,
    ),
    Tool(
        name="restart_container_app_revision",
        description="Restart a specific revision of a Container App. Use list_container_app_revisions first to get the revision name.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "app_name": {"type": "string"},
                "revision_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "app_name", "revision_name"],
        },
        func=_restart_container_app_revision,
        destructive=True,
    ),
    Tool(
        name="list_managed_environments",
        description="List Container App Environments (managed environments) in a resource group.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group"],
        },
        func=_list_managed_environments,
    ),
]
