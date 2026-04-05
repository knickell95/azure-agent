"""Tools for Azure Monitor Diagnostic Settings."""
from azure.mgmt.monitor import MonitorManagementClient
from config import credential
from tools.base import Tool


def _client(subscription_id: str) -> MonitorManagementClient:
    return MonitorManagementClient(credential, subscription_id)


def _list_diagnostic_settings(subscription_id: str, resource_id: str) -> str:
    settings = list(_client(subscription_id).diagnostic_settings.list(resource_id))
    if not settings:
        return f"No diagnostic settings found on resource '{resource_id}'."
    lines = []
    for s in settings:
        destinations = []
        if s.workspace_id:
            destinations.append(f"log-analytics={s.workspace_id.split('/')[-1]}")
        if s.storage_account_id:
            destinations.append(f"storage={s.storage_account_id.split('/')[-1]}")
        if s.event_hub_name:
            destinations.append(f"event-hub={s.event_hub_name}")
        dest_str = ", ".join(destinations) if destinations else "no destinations"
        log_count = len(s.logs or [])
        metric_count = len(s.metrics or [])
        lines.append(f"- {s.name}  logs={log_count}  metrics={metric_count}  destinations=[{dest_str}]")
    return "\n".join(lines)


def _get_diagnostic_setting(
    subscription_id: str,
    resource_id: str,
    setting_name: str,
) -> str:
    s = _client(subscription_id).diagnostic_settings.get(resource_id, setting_name)

    lines = [f"Diagnostic setting: {s.name}"]

    if s.workspace_id:
        lines.append(f"  Log Analytics workspace: {s.workspace_id}")
    if s.storage_account_id:
        lines.append(f"  Storage account:         {s.storage_account_id}")
    if s.event_hub_authorization_rule_id:
        lines.append(f"  Event Hub auth rule:      {s.event_hub_authorization_rule_id}")
    if s.event_hub_name:
        lines.append(f"  Event Hub:               {s.event_hub_name}")

    if s.logs:
        lines.append(f"\n  Log categories ({len(s.logs)}):")
        for log in s.logs:
            enabled = "enabled" if log.enabled else "disabled"
            retention = ""
            if log.retention_policy and log.retention_policy.enabled:
                retention = f"  retention={log.retention_policy.days}d"
            lines.append(f"    - {log.category or log.category_group}  {enabled}{retention}")

    if s.metrics:
        lines.append(f"\n  Metric categories ({len(s.metrics)}):")
        for m in s.metrics:
            enabled = "enabled" if m.enabled else "disabled"
            retention = ""
            if m.retention_policy and m.retention_policy.enabled:
                retention = f"  retention={m.retention_policy.days}d"
            lines.append(f"    - {m.category}  {enabled}{retention}")

    return "\n".join(lines)


def _create_or_update_diagnostic_setting(
    subscription_id: str,
    resource_id: str,
    setting_name: str,
    log_categories: list[str] | None = None,
    enable_all_logs: bool = False,
    metric_categories: list[str] | None = None,
    workspace_id: str | None = None,
    storage_account_id: str | None = None,
    event_hub_authorization_rule_id: str | None = None,
    event_hub_name: str | None = None,
    log_retention_days: int = 0,
) -> str:
    if not any([workspace_id, storage_account_id, event_hub_authorization_rule_id]):
        return "[Error] At least one destination must be specified: workspace_id, storage_account_id, or event_hub_authorization_rule_id."

    retention_policy = {"enabled": log_retention_days > 0, "days": log_retention_days}

    logs = []
    if enable_all_logs:
        logs.append({"category_group": "allLogs", "enabled": True, "retention_policy": retention_policy})
    elif log_categories:
        for cat in log_categories:
            logs.append({"category": cat, "enabled": True, "retention_policy": retention_policy})

    metrics = []
    for cat in (metric_categories or []):
        metrics.append({"category": cat, "enabled": True, "retention_policy": retention_policy})

    params = {
        "logs": logs,
        "metrics": metrics,
    }
    if workspace_id:
        params["workspace_id"] = workspace_id
    if storage_account_id:
        params["storage_account_id"] = storage_account_id
    if event_hub_authorization_rule_id:
        params["event_hub_authorization_rule_id"] = event_hub_authorization_rule_id
    if event_hub_name:
        params["event_hub_name"] = event_hub_name

    s = _client(subscription_id).diagnostic_settings.create_or_update(
        resource_id, setting_name, params
    )

    destinations = []
    if s.workspace_id:
        destinations.append(f"log-analytics={s.workspace_id.split('/')[-1]}")
    if s.storage_account_id:
        destinations.append(f"storage={s.storage_account_id.split('/')[-1]}")
    if s.event_hub_name:
        destinations.append(f"event-hub={s.event_hub_name}")

    return (
        f"Diagnostic setting '{s.name}' saved on resource '{resource_id}'.\n"
        f"  Destinations: {', '.join(destinations)}\n"
        f"  Logs: {len(s.logs or [])}  Metrics: {len(s.metrics or [])}"
    )


def _delete_diagnostic_setting(
    subscription_id: str,
    resource_id: str,
    setting_name: str,
) -> str:
    _client(subscription_id).diagnostic_settings.delete(resource_id, setting_name)
    return f"Diagnostic setting '{setting_name}' has been deleted from resource '{resource_id}'."


TOOLS = [
    Tool(
        name="list_diagnostic_settings",
        description=(
            "List all diagnostic settings configured on an Azure resource. "
            "Shows each setting's name, destination types, and the number of log and metric categories enabled."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_id": {
                    "type": "string",
                    "description": "Full ARM resource ID, e.g. /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Compute/virtualMachines/{name}.",
                },
            },
            "required": ["subscription_id", "resource_id"],
        },
        func=_list_diagnostic_settings,
    ),
    Tool(
        name="get_diagnostic_setting",
        description=(
            "Get full details of a single diagnostic setting on an Azure resource, including all "
            "log and metric categories, their enabled state, retention policy, and configured destinations."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_id": {"type": "string", "description": "Full ARM resource ID of the target resource."},
                "setting_name": {"type": "string", "description": "Name of the diagnostic setting."},
            },
            "required": ["subscription_id", "resource_id", "setting_name"],
        },
        func=_get_diagnostic_setting,
    ),
    Tool(
        name="create_or_update_diagnostic_setting",
        description=(
            "Create or update a diagnostic setting on any Azure resource. "
            "At least one destination must be provided (Log Analytics workspace, storage account, or Event Hub). "
            "Use enable_all_logs=true to capture all log categories without listing them individually. "
            "Set log_retention_days=0 to inherit the workspace or storage retention policy."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_id": {"type": "string", "description": "Full ARM resource ID of the target resource."},
                "setting_name": {"type": "string", "description": "Name for the diagnostic setting (unique per resource)."},
                "enable_all_logs": {
                    "type": "boolean",
                    "default": False,
                    "description": "Set to true to enable the 'allLogs' category group, capturing all log categories the resource supports.",
                },
                "log_categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific log category names to enable. Ignored when enable_all_logs is true.",
                },
                "metric_categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Metric category names to enable, e.g. ['AllMetrics'].",
                },
                "workspace_id": {
                    "type": "string",
                    "description": "Full ARM resource ID of the Log Analytics workspace destination.",
                },
                "storage_account_id": {
                    "type": "string",
                    "description": "Full ARM resource ID of the storage account destination.",
                },
                "event_hub_authorization_rule_id": {
                    "type": "string",
                    "description": "Full ARM resource ID of the Event Hub namespace authorization rule.",
                },
                "event_hub_name": {
                    "type": "string",
                    "description": "Optional Event Hub name within the namespace. Omit to use the default event hub.",
                },
                "log_retention_days": {
                    "type": "integer",
                    "default": 0,
                    "description": "Number of days to retain logs and metrics. 0 means inherit the destination's own retention policy.",
                },
            },
            "required": ["subscription_id", "resource_id", "setting_name"],
        },
        func=_create_or_update_diagnostic_setting,
    ),
    Tool(
        name="delete_diagnostic_setting",
        description="Permanently delete a diagnostic setting from an Azure resource.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_id": {"type": "string", "description": "Full ARM resource ID of the target resource."},
                "setting_name": {"type": "string", "description": "Name of the diagnostic setting to delete."},
            },
            "required": ["subscription_id", "resource_id", "setting_name"],
        },
        func=_delete_diagnostic_setting,
        destructive=True,
    ),
]
