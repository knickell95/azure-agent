"""Tools for Azure Monitor Diagnostic Settings.

Diagnostic settings are not exposed by azure-mgmt-monitor v5+.
All operations use the ARM REST API directly via the microsoft.insights
provider, following the same pattern as tools/policy.py.
"""
import requests
from config import credential
from tools.base import Tool

_ARM_BASE = "https://management.azure.com"
_DIAG_API = "2021-05-01-preview"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _token() -> str:
    return credential.get_token("https://management.azure.com/.default").token


def _headers() -> dict:
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


def _get(url: str) -> dict:
    resp = requests.get(url, headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def _put(url: str, body: dict) -> dict:
    resp = requests.put(url, headers=_headers(), json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _delete_req(url: str) -> None:
    resp = requests.delete(url, headers=_headers(), timeout=30)
    resp.raise_for_status()


def _diag_url(resource_id: str, setting_name: str | None = None) -> str:
    base = f"{_ARM_BASE}{resource_id}/providers/microsoft.insights/diagnosticSettings"
    if setting_name:
        return f"{base}/{setting_name}?api-version={_DIAG_API}"
    return f"{base}?api-version={_DIAG_API}"


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

def _list_diagnostic_settings(subscription_id: str, resource_id: str) -> str:
    data = _get(_diag_url(resource_id))
    settings = data.get("value", [])
    if not settings:
        return f"No diagnostic settings found on resource '{resource_id}'."
    lines = []
    for s in settings:
        props = s.get("properties", {})
        destinations = []
        if props.get("workspaceId"):
            destinations.append(f"log-analytics={props['workspaceId'].split('/')[-1]}")
        if props.get("storageAccountId"):
            destinations.append(f"storage={props['storageAccountId'].split('/')[-1]}")
        if props.get("eventHubName"):
            destinations.append(f"event-hub={props['eventHubName']}")
        dest_str = ", ".join(destinations) if destinations else "no destinations"
        log_count = len(props.get("logs", []))
        metric_count = len(props.get("metrics", []))
        lines.append(
            f"- {s['name']}  logs={log_count}  metrics={metric_count}  "
            f"destinations=[{dest_str}]"
        )
    return "\n".join(lines)


def _get_diagnostic_setting(
    subscription_id: str,
    resource_id: str,
    setting_name: str,
) -> str:
    s = _get(_diag_url(resource_id, setting_name))
    props = s.get("properties", {})

    lines = [f"Diagnostic setting: {s['name']}"]

    if props.get("workspaceId"):
        lines.append(f"  Log Analytics workspace: {props['workspaceId']}")
    if props.get("storageAccountId"):
        lines.append(f"  Storage account:         {props['storageAccountId']}")
    if props.get("eventHubAuthorizationRuleId"):
        lines.append(f"  Event Hub auth rule:      {props['eventHubAuthorizationRuleId']}")
    if props.get("eventHubName"):
        lines.append(f"  Event Hub:               {props['eventHubName']}")

    logs = props.get("logs", [])
    if logs:
        lines.append(f"\n  Log categories ({len(logs)}):")
        for log in logs:
            enabled = "enabled" if log.get("enabled") else "disabled"
            category = log.get("category") or log.get("categoryGroup", "n/a")
            retention = ""
            rp = log.get("retentionPolicy", {})
            if rp.get("enabled"):
                retention = f"  retention={rp['days']}d"
            lines.append(f"    - {category}  {enabled}{retention}")

    metrics = props.get("metrics", [])
    if metrics:
        lines.append(f"\n  Metric categories ({len(metrics)}):")
        for m in metrics:
            enabled = "enabled" if m.get("enabled") else "disabled"
            retention = ""
            rp = m.get("retentionPolicy", {})
            if rp.get("enabled"):
                retention = f"  retention={rp['days']}d"
            lines.append(f"    - {m.get('category', 'n/a')}  {enabled}{retention}")

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
        logs.append({"categoryGroup": "allLogs", "enabled": True, "retentionPolicy": retention_policy})
    elif log_categories:
        for cat in log_categories:
            logs.append({"category": cat, "enabled": True, "retentionPolicy": retention_policy})

    metrics = []
    for cat in (metric_categories or []):
        metrics.append({"category": cat, "enabled": True, "retentionPolicy": retention_policy})

    props: dict = {"logs": logs, "metrics": metrics}
    if workspace_id:
        props["workspaceId"] = workspace_id
    if storage_account_id:
        props["storageAccountId"] = storage_account_id
    if event_hub_authorization_rule_id:
        props["eventHubAuthorizationRuleId"] = event_hub_authorization_rule_id
    if event_hub_name:
        props["eventHubName"] = event_hub_name

    result = _put(_diag_url(resource_id, setting_name), {"properties": props})
    rprops = result.get("properties", {})

    destinations = []
    if rprops.get("workspaceId"):
        destinations.append(f"log-analytics={rprops['workspaceId'].split('/')[-1]}")
    if rprops.get("storageAccountId"):
        destinations.append(f"storage={rprops['storageAccountId'].split('/')[-1]}")
    if rprops.get("eventHubName"):
        destinations.append(f"event-hub={rprops['eventHubName']}")

    return (
        f"Diagnostic setting '{result['name']}' saved on resource '{resource_id}'.\n"
        f"  Destinations: {', '.join(destinations)}\n"
        f"  Logs: {len(rprops.get('logs', []))}  Metrics: {len(rprops.get('metrics', []))}"
    )


def _delete_diagnostic_setting(
    subscription_id: str,
    resource_id: str,
    setting_name: str,
) -> str:
    _delete_req(_diag_url(resource_id, setting_name))
    return f"Diagnostic setting '{setting_name}' has been deleted from resource '{resource_id}'."


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

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
