"""Tools for Azure Policy — definitions, assignments, initiatives, and compliance.

All operations use the Azure Management REST API directly:
- PolicyClient was removed from azure-mgmt-resource in v22+.
- azure-mgmt-policyinsights (all versions) requires 'six' (Python 2 compat shim)
  and is incompatible with current azure-sdk-for-python packages.
"""
import json
from datetime import datetime, timedelta, timezone

import requests

from config import credential
from tools.base import Tool

_ARM_BASE = "https://management.azure.com"
_POLICY_API = "2023-04-01"
_ASSIGNMENT_API = "2022-06-01"
_INSIGHTS_API = "2019-10-01"
_REMEDIATION_API = "2021-10-01"


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


def _post(url: str, body: dict | None = None) -> dict:
    resp = requests.post(url, headers=_headers(), json=body or {}, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Policy Definitions
# ---------------------------------------------------------------------------

def _list_policy_definitions(subscription_id: str, policy_type: str = "all") -> str:
    url = (
        f"{_ARM_BASE}/subscriptions/{subscription_id}/providers/"
        f"Microsoft.Authorization/policyDefinitions?api-version={_POLICY_API}"
    )
    data = _get(url)
    defs = data.get("value", [])
    if policy_type != "all":
        defs = [d for d in defs if d.get("properties", {}).get("policyType", "").lower() == policy_type.lower()]
    if not defs:
        return f"No {policy_type} policy definitions found."
    lines = [
        f"- [{d['properties'].get('policyType', '?')}] {d['properties'].get('displayName', d['name'])}  id={d['name']}"
        for d in sorted(defs, key=lambda x: x["properties"].get("displayName", ""))
    ]
    return "\n".join(lines[:100]) + (f"\n... ({len(defs)} total)" if len(defs) > 100 else "")


def _get_policy_definition(subscription_id: str, policy_name: str) -> str:
    # Try built-in first, then subscription-scoped custom
    for url in [
        f"{_ARM_BASE}/providers/Microsoft.Authorization/policyDefinitions/{policy_name}?api-version={_POLICY_API}",
        f"{_ARM_BASE}/subscriptions/{subscription_id}/providers/Microsoft.Authorization/policyDefinitions/{policy_name}?api-version={_POLICY_API}",
    ]:
        try:
            d = _get(url)
            props = d.get("properties", {})
            params = props.get("parameters", {})
            def _param_default(v):
                return "(required)" if "defaultValue" not in v else f"default={v['defaultValue']}"
            param_lines = "\n".join(
                f"    - {k}: {v.get('type', '?')} {_param_default(v)}"
                for k, v in params.items()
            )
            return (
                f"Name: {d['name']}\n"
                f"Display name: {props.get('displayName', 'n/a')}\n"
                f"Type: {props.get('policyType', 'n/a')}\n"
                f"Mode: {props.get('mode', 'n/a')}\n"
                f"Description: {props.get('description', 'n/a')}\n"
                + (f"Parameters:\n{param_lines}" if param_lines else "")
            )
        except requests.HTTPError as exc:
            if exc.response.status_code == 404:
                continue
            return f"[Azure error] {exc}"
    return f"Policy definition '{policy_name}' not found."


def _create_custom_policy_definition(
    subscription_id: str,
    policy_name: str,
    display_name: str,
    description: str,
    policy_rule_json: str,
    mode: str = "All",
    parameters_json: str = "{}",
) -> str:
    try:
        policy_rule = json.loads(policy_rule_json)
        parameters = json.loads(parameters_json)
    except json.JSONDecodeError as exc:
        return f"Invalid JSON: {exc}"

    url = (
        f"{_ARM_BASE}/subscriptions/{subscription_id}/providers/"
        f"Microsoft.Authorization/policyDefinitions/{policy_name}?api-version={_POLICY_API}"
    )
    body = {
        "properties": {
            "displayName": display_name,
            "description": description,
            "policyType": "Custom",
            "mode": mode,
            "policyRule": policy_rule,
            "parameters": parameters,
        }
    }
    result = _put(url, body)
    return f"Custom policy '{result['properties']['displayName']}' (id={result['name']}) created."


def _delete_custom_policy_definition(subscription_id: str, policy_name: str) -> str:
    url = (
        f"{_ARM_BASE}/subscriptions/{subscription_id}/providers/"
        f"Microsoft.Authorization/policyDefinitions/{policy_name}?api-version={_POLICY_API}"
    )
    _delete_req(url)
    return f"Custom policy definition '{policy_name}' deleted."


# ---------------------------------------------------------------------------
# Policy Initiatives (Policy Set Definitions)
# ---------------------------------------------------------------------------

def _list_policy_initiatives(subscription_id: str, policy_type: str = "all") -> str:
    url = (
        f"{_ARM_BASE}/subscriptions/{subscription_id}/providers/"
        f"Microsoft.Authorization/policySetDefinitions?api-version={_POLICY_API}"
    )
    data = _get(url)
    initiatives = data.get("value", [])
    if policy_type != "all":
        initiatives = [i for i in initiatives if i.get("properties", {}).get("policyType", "").lower() == policy_type.lower()]
    if not initiatives:
        return f"No {policy_type} policy initiatives found."
    lines = [
        f"- [{i['properties'].get('policyType', '?')}] "
        f"{i['properties'].get('displayName', i['name'])}  "
        f"policies={len(i['properties'].get('policyDefinitions', []))}  id={i['name']}"
        for i in sorted(initiatives, key=lambda x: x["properties"].get("displayName", ""))
    ]
    return "\n".join(lines[:100]) + (f"\n... ({len(initiatives)} total)" if len(initiatives) > 100 else "")


def _get_policy_initiative(subscription_id: str, initiative_name: str) -> str:
    for url in [
        f"{_ARM_BASE}/providers/Microsoft.Authorization/policySetDefinitions/{initiative_name}?api-version={_POLICY_API}",
        f"{_ARM_BASE}/subscriptions/{subscription_id}/providers/Microsoft.Authorization/policySetDefinitions/{initiative_name}?api-version={_POLICY_API}",
    ]:
        try:
            i = _get(url)
            props = i.get("properties", {})
            policy_defs = props.get("policyDefinitions", [])
            policies = "\n".join(
                f"  - {p['policyDefinitionId'].split('/')[-1]}" for p in policy_defs
            )
            return (
                f"Initiative: {props.get('displayName', i['name'])}\n"
                f"Type: {props.get('policyType', 'n/a')}\n"
                f"Description: {props.get('description', 'n/a')}\n"
                f"Included policies ({len(policy_defs)}):\n{policies}"
            )
        except requests.HTTPError as exc:
            if exc.response.status_code == 404:
                continue
            return f"[Azure error] {exc}"
    return f"Initiative '{initiative_name}' not found."


# ---------------------------------------------------------------------------
# Policy Assignments
# ---------------------------------------------------------------------------

def _list_policy_assignments(subscription_id: str, resource_group: str | None = None) -> str:
    if resource_group:
        url = (
            f"{_ARM_BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/"
            f"Microsoft.Authorization/policyAssignments?api-version={_ASSIGNMENT_API}"
        )
    else:
        url = (
            f"{_ARM_BASE}/subscriptions/{subscription_id}/providers/"
            f"Microsoft.Authorization/policyAssignments?api-version={_ASSIGNMENT_API}"
        )
    data = _get(url)
    assignments = data.get("value", [])
    if not assignments:
        return "No policy assignments found at this scope."
    lines = [
        f"- {a['properties'].get('displayName', a['name'])}  "
        f"id={a['name']}  enforcement={a['properties'].get('enforcementMode', 'n/a')}  "
        f"scope={a['properties'].get('scope', 'n/a')}"
        for a in assignments
    ]
    return "\n".join(lines)


def _get_policy_assignment(subscription_id: str, assignment_name: str, scope: str) -> str:
    url = f"{_ARM_BASE}{scope}/providers/Microsoft.Authorization/policyAssignments/{assignment_name}?api-version={_ASSIGNMENT_API}"
    a = _get(url)
    props = a.get("properties", {})
    return (
        f"Assignment: {props.get('displayName', a['name'])}\n"
        f"  Policy/Initiative: {props.get('policyDefinitionId', 'n/a')}\n"
        f"  Scope: {props.get('scope', 'n/a')}\n"
        f"  Enforcement mode: {props.get('enforcementMode', 'n/a')}\n"
        f"  Description: {props.get('description', 'n/a')}"
    )


def _create_policy_assignment(
    subscription_id: str,
    assignment_name: str,
    display_name: str,
    policy_definition_id: str,
    scope: str,
    enforcement_mode: str = "Default",
    description: str = "",
    parameters_json: str = "{}",
    identity_type: str = "None",
    user_assigned_identity_id: str = "",
    location: str = "",
) -> str:
    try:
        parameters = json.loads(parameters_json)
    except json.JSONDecodeError as exc:
        return f"Invalid JSON in parameters: {exc}"

    if identity_type != "None" and not location:
        return "[Error] A location is required when assigning a managed identity to a policy assignment."

    if identity_type == "UserAssigned" and not user_assigned_identity_id:
        return "[Error] user_assigned_identity_id is required when identity_type is 'UserAssigned'."

    url = f"{_ARM_BASE}{scope}/providers/Microsoft.Authorization/policyAssignments/{assignment_name}?api-version={_ASSIGNMENT_API}"
    body = {
        "properties": {
            "displayName": display_name,
            "description": description,
            "policyDefinitionId": policy_definition_id,
            "scope": scope,
            "enforcementMode": enforcement_mode,
            "parameters": parameters,
        }
    }

    if identity_type == "SystemAssigned":
        body["identity"] = {"type": "SystemAssigned"}
        body["location"] = location
    elif identity_type == "UserAssigned":
        body["identity"] = {
            "type": "UserAssigned",
            "userAssignedIdentities": {user_assigned_identity_id: {}},
        }
        body["location"] = location

    result = _put(url, body)
    props = result.get("properties", {})
    identity = result.get("identity", {})
    identity_type_out = identity.get("type", "None")

    lines = [
        f"Policy assignment '{props.get('displayName', result['name'])}' created.",
        f"  Scope:       {props.get('scope', 'n/a')}",
        f"  Enforcement: {props.get('enforcementMode', 'n/a')}",
    ]
    if identity_type_out != "None":
        lines.append(f"  Identity:    {identity_type_out}")
        if identity_type_out == "SystemAssigned":
            lines.append(f"  Principal ID: {identity.get('principalId', 'n/a')}")
    return "\n".join(lines)


def _delete_policy_assignment(subscription_id: str, scope: str, assignment_name: str) -> str:
    url = f"{_ARM_BASE}{scope}/providers/Microsoft.Authorization/policyAssignments/{assignment_name}?api-version={_ASSIGNMENT_API}"
    _delete_req(url)
    return f"Policy assignment '{assignment_name}' at scope '{scope}' deleted."


# ---------------------------------------------------------------------------
# Policy Compliance
# ---------------------------------------------------------------------------

def _get_compliance_summary(subscription_id: str, resource_group: str | None = None) -> str:
    if resource_group:
        url = (
            f"{_ARM_BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/"
            f"Microsoft.PolicyInsights/policyStates/latest/summarize?api-version={_INSIGHTS_API}"
        )
    else:
        url = (
            f"{_ARM_BASE}/subscriptions/{subscription_id}/providers/"
            f"Microsoft.PolicyInsights/policyStates/latest/summarize?api-version={_INSIGHTS_API}"
        )
    data = _post(url)
    values = data.get("value", [])
    if not values:
        return "No compliance data available."
    r = values[0].get("results", {})
    scope_label = f"resource group '{resource_group}'" if resource_group else f"subscription {subscription_id}"
    return (
        f"Compliance summary for {scope_label}:\n"
        f"  Non-compliant resources: {r.get('nonCompliantResources', 'n/a')}\n"
        f"  Non-compliant policies:  {r.get('nonCompliantPolicies', 'n/a')}"
    )


def _list_non_compliant_resources(
    subscription_id: str,
    resource_group: str | None = None,
    policy_assignment_name: str | None = None,
) -> str:
    filter_str = "complianceState eq 'NonCompliant'"
    if policy_assignment_name:
        filter_str += f" and policyAssignmentName eq '{policy_assignment_name}'"

    if resource_group:
        url = (
            f"{_ARM_BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/"
            f"Microsoft.PolicyInsights/policyStates/latest/queryResults"
            f"?api-version={_INSIGHTS_API}&$filter={filter_str}&$top=50"
        )
    else:
        url = (
            f"{_ARM_BASE}/subscriptions/{subscription_id}/providers/"
            f"Microsoft.PolicyInsights/policyStates/latest/queryResults"
            f"?api-version={_INSIGHTS_API}&$filter={filter_str}&$top=50"
        )
    data = _post(url)
    states = data.get("value", [])
    if not states:
        return "No non-compliant resources found."

    lines = [
        f"- {s.get('resourceId', '').split('/')[-1]}  type={s.get('resourceType', 'n/a')}  "
        f"policy={s.get('policyDefinitionName', 'n/a')}  assignment={s.get('policyAssignmentName', 'n/a')}"
        for s in states
    ]
    suffix = "\n(showing up to 50 results)" if len(states) == 50 else ""
    return "\n".join(lines) + suffix


def _list_policy_events(
    subscription_id: str,
    resource_group: str | None = None,
    days: int = 7,
) -> str:
    from_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if resource_group:
        url = (
            f"{_ARM_BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/"
            f"Microsoft.PolicyInsights/policyEvents/default/queryResults"
            f"?api-version={_INSIGHTS_API}&$from={from_date}&$top=30"
        )
    else:
        url = (
            f"{_ARM_BASE}/subscriptions/{subscription_id}/providers/"
            f"Microsoft.PolicyInsights/policyEvents/default/queryResults"
            f"?api-version={_INSIGHTS_API}&$from={from_date}&$top=30"
        )
    data = _post(url)
    events = data.get("value", [])
    if not events:
        return f"No policy events in the last {days} days."

    lines = [
        f"- {e.get('timestamp', '')[:19]}  {e.get('complianceState', 'n/a')}  "
        f"resource={e.get('resourceId', '').split('/')[-1]}  policy={e.get('policyDefinitionName', 'n/a')}"
        for e in events
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Policy Remediation
# ---------------------------------------------------------------------------

def _list_remediations(subscription_id: str, resource_group: str | None = None) -> str:
    if resource_group:
        url = (
            f"{_ARM_BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/"
            f"Microsoft.PolicyInsights/remediations?api-version={_REMEDIATION_API}"
        )
    else:
        url = (
            f"{_ARM_BASE}/subscriptions/{subscription_id}/providers/"
            f"Microsoft.PolicyInsights/remediations?api-version={_REMEDIATION_API}"
        )
    data = _get(url)
    remediations = data.get("value", [])
    if not remediations:
        return "No remediation tasks found."
    lines = [
        f"- {r['name']}  "
        f"assignment={r['properties'].get('policyAssignmentId', '').split('/')[-1]}  "
        f"status={r['properties'].get('provisioningState', 'n/a')}"
        for r in remediations
    ]
    return "\n".join(lines)


def _create_remediation(
    subscription_id: str,
    remediation_name: str,
    policy_assignment_id: str,
    resource_group: str | None = None,
) -> str:
    if resource_group:
        url = (
            f"{_ARM_BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/"
            f"Microsoft.PolicyInsights/remediations/{remediation_name}?api-version={_REMEDIATION_API}"
        )
    else:
        url = (
            f"{_ARM_BASE}/subscriptions/{subscription_id}/providers/"
            f"Microsoft.PolicyInsights/remediations/{remediation_name}?api-version={_REMEDIATION_API}"
        )
    body = {"properties": {"policyAssignmentId": policy_assignment_id}}
    result = _put(url, body)
    props = result.get("properties", {})
    return (
        f"Remediation task '{result['name']}' created.\n"
        f"  Assignment: {props.get('policyAssignmentId', '').split('/')[-1]}\n"
        f"  Status: {props.get('provisioningState', 'n/a')}"
    )


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS = [
    Tool(
        name="list_policy_definitions",
        description="List Azure policy definitions. Set policy_type to 'BuiltIn', 'Custom', or 'all' (default).",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "policy_type": {"type": "string", "enum": ["all", "BuiltIn", "Custom"], "default": "all"},
            },
            "required": ["subscription_id"],
        },
        func=_list_policy_definitions,
    ),
    Tool(
        name="get_policy_definition",
        description="Get full details of a policy definition by its name/GUID.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "policy_name": {"type": "string"},
            },
            "required": ["subscription_id", "policy_name"],
        },
        func=_get_policy_definition,
    ),
    Tool(
        name="create_custom_policy_definition",
        description="Create a new custom policy definition. Provide policy_rule_json as a JSON string.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "policy_name": {"type": "string", "description": "Unique short name (no spaces)."},
                "display_name": {"type": "string"},
                "description": {"type": "string"},
                "policy_rule_json": {"type": "string", "description": 'JSON string, e.g. {"if":{...},"then":{"effect":"deny"}}.'},
                "mode": {"type": "string", "enum": ["All", "Indexed"], "default": "All"},
                "parameters_json": {"type": "string", "default": "{}"},
            },
            "required": ["subscription_id", "policy_name", "display_name", "description", "policy_rule_json"],
        },
        func=_create_custom_policy_definition,
    ),
    Tool(
        name="delete_custom_policy_definition",
        description="Delete a custom policy definition. Built-in policies cannot be deleted.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "policy_name": {"type": "string"},
            },
            "required": ["subscription_id", "policy_name"],
        },
        func=_delete_custom_policy_definition,
        destructive=True,
    ),
    Tool(
        name="list_policy_initiatives",
        description="List policy initiatives (policy set definitions). Set policy_type to 'BuiltIn', 'Custom', or 'all'.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "policy_type": {"type": "string", "enum": ["all", "BuiltIn", "Custom"], "default": "all"},
            },
            "required": ["subscription_id"],
        },
        func=_list_policy_initiatives,
    ),
    Tool(
        name="get_policy_initiative",
        description="Get details of a policy initiative including its constituent policies.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "initiative_name": {"type": "string"},
            },
            "required": ["subscription_id", "initiative_name"],
        },
        func=_get_policy_initiative,
    ),
    Tool(
        name="list_policy_assignments",
        description="List policy assignments at subscription or resource group scope.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string", "description": "Optional. Omit for subscription scope."},
            },
            "required": ["subscription_id"],
        },
        func=_list_policy_assignments,
    ),
    Tool(
        name="get_policy_assignment",
        description="Get details of a specific policy assignment.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "assignment_name": {"type": "string"},
                "scope": {"type": "string", "description": "ARM scope path, e.g. /subscriptions/{id}/resourceGroups/{rg}."},
            },
            "required": ["subscription_id", "assignment_name", "scope"],
        },
        func=_get_policy_assignment,
    ),
    Tool(
        name="create_policy_assignment",
        description=(
            "Assign a policy or initiative to a scope. "
            "Use enforcement_mode='DoNotEnforce' for audit-only. "
            "Policies with 'deployIfNotExists' or 'modify' effects require a managed identity — "
            "set identity_type to 'SystemAssigned' or 'UserAssigned' and provide a location. "
            "After creating an assignment with a system-assigned identity, grant it the appropriate "
            "role (e.g. Contributor) using create_role_assignment with the returned principal ID."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "assignment_name": {"type": "string"},
                "display_name": {"type": "string"},
                "policy_definition_id": {"type": "string", "description": "Full ARM resource ID of the policy or initiative."},
                "scope": {"type": "string", "description": "ARM scope, e.g. /subscriptions/{id} or /subscriptions/{id}/resourceGroups/{rg}."},
                "enforcement_mode": {"type": "string", "enum": ["Default", "DoNotEnforce"], "default": "Default"},
                "description": {"type": "string", "default": ""},
                "parameters_json": {"type": "string", "default": "{}"},
                "identity_type": {
                    "type": "string",
                    "enum": ["None", "SystemAssigned", "UserAssigned"],
                    "default": "None",
                    "description": "Managed identity type to attach to the assignment. Required for deployIfNotExists and modify policies.",
                },
                "user_assigned_identity_id": {
                    "type": "string",
                    "description": "Full ARM resource ID of the user-assigned managed identity. Required when identity_type is 'UserAssigned'.",
                },
                "location": {
                    "type": "string",
                    "description": "Azure region for the assignment, e.g. eastus. Required when identity_type is not 'None'.",
                },
            },
            "required": ["subscription_id", "assignment_name", "display_name", "policy_definition_id", "scope"],
        },
        func=_create_policy_assignment,
    ),
    Tool(
        name="delete_policy_assignment",
        description="Remove a policy assignment from a scope.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "scope": {"type": "string"},
                "assignment_name": {"type": "string"},
            },
            "required": ["subscription_id", "scope", "assignment_name"],
        },
        func=_delete_policy_assignment,
        destructive=True,
    ),
    Tool(
        name="get_policy_compliance_summary",
        description="Get a high-level compliance summary showing non-compliant resources and policies.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string", "description": "Optional."},
            },
            "required": ["subscription_id"],
        },
        func=_get_compliance_summary,
    ),
    Tool(
        name="list_non_compliant_resources",
        description="List resources that are non-compliant with policy. Optionally filter by assignment.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string", "description": "Optional."},
                "policy_assignment_name": {"type": "string", "description": "Optional. Filter by assignment name."},
            },
            "required": ["subscription_id"],
        },
        func=_list_non_compliant_resources,
    ),
    Tool(
        name="list_policy_events",
        description="List recent policy evaluation events for audit trail purposes.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string", "description": "Optional."},
                "days": {"type": "integer", "default": 7},
            },
            "required": ["subscription_id"],
        },
        func=_list_policy_events,
    ),
    Tool(
        name="list_policy_remediations",
        description="List policy remediation tasks at subscription or resource group scope.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string", "description": "Optional."},
            },
            "required": ["subscription_id"],
        },
        func=_list_remediations,
    ),
    Tool(
        name="create_policy_remediation",
        description="Create a remediation task to bring non-compliant resources into compliance.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "remediation_name": {"type": "string"},
                "policy_assignment_id": {"type": "string", "description": "Full ARM resource ID of the policy assignment."},
                "resource_group": {"type": "string", "description": "Optional. Omit to remediate at subscription scope."},
            },
            "required": ["subscription_id", "remediation_name", "policy_assignment_id"],
        },
        func=_create_remediation,
    ),
]
