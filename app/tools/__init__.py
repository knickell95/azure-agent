"""Tool registry — grouped for dynamic loading."""
from tools.resources import TOOLS as _RESOURCE_TOOLS
from tools.compute import TOOLS as _COMPUTE_TOOLS
from tools.network import TOOLS as _NETWORK_TOOLS
from tools.storage import TOOLS as _STORAGE_TOOLS
from tools.aks import TOOLS as _AKS_TOOLS
from tools.identity import TOOLS as _IDENTITY_TOOLS
from tools.policy import TOOLS as _POLICY_TOOLS
from tools.entra import TOOLS as _ENTRA_TOOLS
from tools.monitor import TOOLS as _MONITOR_TOOLS
from tools.managed_identity import TOOLS as _MANAGED_IDENTITY_TOOLS

# ---------------------------------------------------------------------------
# Tool groups — each value is a list of Tool objects for one service domain.
# "core" is always loaded; all others are selected dynamically per request.
# ---------------------------------------------------------------------------
TOOL_GROUPS: dict[str, list] = {
    # Always included — needed to resolve subscriptions/resource groups before
    # almost any other operation.
    "core":     _RESOURCE_TOOLS,

    # Loaded on demand based on the user's request.
    "compute":  _COMPUTE_TOOLS,
    "network":  _NETWORK_TOOLS,
    "storage":  _STORAGE_TOOLS,
    "aks":      _AKS_TOOLS,
    "identity": _IDENTITY_TOOLS,
    "policy":   _POLICY_TOOLS,
    "entra":    _ENTRA_TOOLS,
    "monitor":          _MONITOR_TOOLS,
    "managed_identity": _MANAGED_IDENTITY_TOOLS,
}

# Short descriptions used by the Haiku classifier to pick groups.
GROUP_DESCRIPTIONS: dict[str, str] = {
    "compute":  "virtual machines, VM sizes, disks, start/stop/create/delete VMs",
    "network":  "virtual networks, subnets, NSGs, network security groups, public IPs, VNets",
    "storage":  "storage accounts, blob containers",
    "aks":      "AKS clusters, Kubernetes, node pools, container service",
    "identity": "RBAC, role assignments, role definitions, Azure permissions",
    "policy":   "Azure Policy, policy definitions, initiatives, assignments, compliance, remediation",
    "entra":    "Entra ID, Azure AD, users, groups, app registrations, service principals, devices, directory roles",
    "monitor":          "Azure Monitor, diagnostic settings, logs, metrics, Log Analytics workspace, Event Hub",
    "managed_identity": "managed identity, user-assigned identity, MSI, service identity, principal ID, client ID",
}

# Complete flat list and registry — used for tool execution lookup regardless
# of which groups are active in a given request.
ALL_TOOLS = [t for tools in TOOL_GROUPS.values() for t in tools]
TOOL_REGISTRY: dict = {tool.name: tool for tool in ALL_TOOLS}


def definitions_for_groups(group_names: list[str], provider: str = "anthropic") -> list[dict]:
    """Return tool definitions for core + the requested groups.

    For Anthropic: uses the native definition format and adds cache_control to
    the last entry so the tool list is prompt-cached.
    For OpenAI: uses the function-call format; no cache_control.
    """
    selected: list = list(TOOL_GROUPS["core"])
    for name in group_names:
        if name in TOOL_GROUPS and name != "core":
            selected.extend(TOOL_GROUPS[name])

    if provider == "openai":
        return [t.openai_definition for t in selected]

    defs = [t.definition for t in selected]
    if defs:
        defs[-1] = {**defs[-1], "cache_control": {"type": "ephemeral"}}
    return defs
