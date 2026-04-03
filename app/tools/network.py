"""Tools for virtual networks, subnets, NSGs, and public IPs."""
from azure.mgmt.network import NetworkManagementClient
from config import credential
from tools.base import Tool


def _client(subscription_id: str) -> NetworkManagementClient:
    return NetworkManagementClient(credential, subscription_id)


def _list_vnets(subscription_id: str, resource_group: str) -> str:
    vnets = list(_client(subscription_id).virtual_networks.list(resource_group))
    if not vnets:
        return f"No VNets found in '{resource_group}'."
    lines = []
    for v in vnets:
        prefixes = ", ".join(v.address_space.address_prefixes) if v.address_space else "n/a"
        lines.append(f"- {v.name}  address={prefixes}  location={v.location}")
    return "\n".join(lines)


def _create_vnet(
    subscription_id: str,
    resource_group: str,
    vnet_name: str,
    location: str,
    address_prefix: str = "10.0.0.0/16",
) -> str:
    vnet = _client(subscription_id).virtual_networks.begin_create_or_update(
        resource_group,
        vnet_name,
        {"location": location, "address_space": {"address_prefixes": [address_prefix]}},
    ).result()
    return f"VNet '{vnet.name}' created with address space {address_prefix} in {vnet.location}."


def _delete_vnet(subscription_id: str, resource_group: str, vnet_name: str) -> str:
    _client(subscription_id).virtual_networks.begin_delete(resource_group, vnet_name).result()
    return f"VNet '{vnet_name}' has been deleted."


def _list_nsgs(subscription_id: str, resource_group: str) -> str:
    nsgs = list(_client(subscription_id).network_security_groups.list(resource_group))
    if not nsgs:
        return f"No NSGs found in '{resource_group}'."
    lines = [f"- {n.name}  location={n.location}  rules={len(n.security_rules or [])}" for n in nsgs]
    return "\n".join(lines)


def _get_nsg_rules(subscription_id: str, resource_group: str, nsg_name: str) -> str:
    nsg = _client(subscription_id).network_security_groups.get(resource_group, nsg_name)
    rules = list(nsg.security_rules or [])
    if not rules:
        return f"NSG '{nsg_name}' has no custom security rules."
    lines = []
    for r in sorted(rules, key=lambda x: x.priority):
        lines.append(
            f"- [{r.priority}] {r.name}  {r.direction} {r.access}  "
            f"proto={r.protocol}  src={r.source_address_prefix}:{r.source_port_range}  "
            f"dst={r.destination_address_prefix}:{r.destination_port_range}"
        )
    return "\n".join(lines)


def _list_public_ips(subscription_id: str, resource_group: str) -> str:
    ips = list(_client(subscription_id).public_ip_addresses.list(resource_group))
    if not ips:
        return f"No public IP addresses found in '{resource_group}'."
    lines = [
        f"- {ip.name}  address={ip.ip_address or 'unassigned'}  sku={ip.sku.name if ip.sku else 'n/a'}"
        for ip in ips
    ]
    return "\n".join(lines)


TOOLS = [
    Tool(
        name="list_virtual_networks",
        description="List all virtual networks (VNets) in a resource group.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group"],
        },
        func=_list_vnets,
    ),
    Tool(
        name="create_virtual_network",
        description="Create a new virtual network with a specified address space.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "vnet_name": {"type": "string"},
                "location": {"type": "string"},
                "address_prefix": {"type": "string", "description": "CIDR block, e.g. 10.0.0.0/16.", "default": "10.0.0.0/16"},
            },
            "required": ["subscription_id", "resource_group", "vnet_name", "location"],
        },
        func=_create_vnet,
    ),
    Tool(
        name="delete_virtual_network",
        description="Permanently delete a virtual network.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "vnet_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "vnet_name"],
        },
        func=_delete_vnet,
        destructive=True,
    ),
    Tool(
        name="list_network_security_groups",
        description="List all network security groups (NSGs) in a resource group.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group"],
        },
        func=_list_nsgs,
    ),
    Tool(
        name="get_nsg_rules",
        description="Get all security rules for a specific NSG.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "nsg_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "nsg_name"],
        },
        func=_get_nsg_rules,
    ),
    Tool(
        name="list_public_ip_addresses",
        description="List all public IP addresses in a resource group.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group"],
        },
        func=_list_public_ips,
    ),
]
