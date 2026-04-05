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


def _create_nsg(
    subscription_id: str,
    resource_group: str,
    nsg_name: str,
    location: str,
) -> str:
    nsg = _client(subscription_id).network_security_groups.begin_create_or_update(
        resource_group,
        nsg_name,
        {"location": location},
    ).result()
    return f"NSG '{nsg.name}' created in '{resource_group}' ({nsg.location})."


def _delete_nsg(subscription_id: str, resource_group: str, nsg_name: str) -> str:
    _client(subscription_id).network_security_groups.begin_delete(resource_group, nsg_name).result()
    return f"NSG '{nsg_name}' has been deleted."


def _create_nsg_rule(
    subscription_id: str,
    resource_group: str,
    nsg_name: str,
    rule_name: str,
    priority: int,
    direction: str,
    access: str,
    protocol: str,
    source_address_prefix: str,
    source_port_range: str,
    destination_address_prefix: str,
    destination_port_range: str,
    description: str = "",
) -> str:
    rule = _client(subscription_id).security_rules.begin_create_or_update(
        resource_group,
        nsg_name,
        rule_name,
        {
            "priority": priority,
            "direction": direction,
            "access": access,
            "protocol": protocol,
            "source_address_prefix": source_address_prefix,
            "source_port_range": source_port_range,
            "destination_address_prefix": destination_address_prefix,
            "destination_port_range": destination_port_range,
            "description": description,
        },
    ).result()
    return (
        f"Rule '{rule.name}' {'updated' if description == '' and rule.description == '' else 'saved'} "
        f"on NSG '{nsg_name}': [{rule.priority}] {rule.direction} {rule.access} "
        f"proto={rule.protocol} "
        f"src={rule.source_address_prefix}:{rule.source_port_range} "
        f"dst={rule.destination_address_prefix}:{rule.destination_port_range}"
    )


def _delete_nsg_rule(
    subscription_id: str,
    resource_group: str,
    nsg_name: str,
    rule_name: str,
) -> str:
    _client(subscription_id).security_rules.begin_delete(resource_group, nsg_name, rule_name).result()
    return f"Security rule '{rule_name}' has been deleted from NSG '{nsg_name}'."


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
        name="create_network_security_group",
        description="Create a new network security group (NSG) in a resource group.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "nsg_name": {"type": "string"},
                "location": {"type": "string", "description": "Azure region, e.g. eastus."},
            },
            "required": ["subscription_id", "resource_group", "nsg_name", "location"],
        },
        func=_create_nsg,
    ),
    Tool(
        name="delete_network_security_group",
        description="Permanently delete a network security group (NSG) and all its rules.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "nsg_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "nsg_name"],
        },
        func=_delete_nsg,
        destructive=True,
    ),
    Tool(
        name="create_or_update_nsg_rule",
        description=(
            "Create a new security rule on an NSG, or update an existing one by rule name. "
            "Priority must be unique within the NSG (100–4096; lower number = higher priority). "
            "Use '*' for protocol, port range, or address prefix to match all values."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "nsg_name": {"type": "string"},
                "rule_name": {"type": "string"},
                "priority": {"type": "integer", "description": "Unique priority 100–4096; lower = evaluated first."},
                "direction": {"type": "string", "enum": ["Inbound", "Outbound"]},
                "access": {"type": "string", "enum": ["Allow", "Deny"]},
                "protocol": {"type": "string", "enum": ["Tcp", "Udp", "Icmp", "*"]},
                "source_address_prefix": {"type": "string", "description": "CIDR, service tag (e.g. Internet, VirtualNetwork), or *."},
                "source_port_range": {"type": "string", "description": "Port, range (e.g. 1024-65535), or *."},
                "destination_address_prefix": {"type": "string", "description": "CIDR, service tag, or *."},
                "destination_port_range": {"type": "string", "description": "Port, range, or *."},
                "description": {"type": "string", "description": "Optional human-readable description of the rule."},
            },
            "required": [
                "subscription_id", "resource_group", "nsg_name", "rule_name",
                "priority", "direction", "access", "protocol",
                "source_address_prefix", "source_port_range",
                "destination_address_prefix", "destination_port_range",
            ],
        },
        func=_create_nsg_rule,
    ),
    Tool(
        name="delete_nsg_rule",
        description="Delete a specific security rule from an NSG by name.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "nsg_name": {"type": "string"},
                "rule_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "nsg_name", "rule_name"],
        },
        func=_delete_nsg_rule,
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
