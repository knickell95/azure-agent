"""Tools for virtual machines and their attached resources."""
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient as _NetworkClient
from config import credential
from tools.base import Tool


def _client(subscription_id: str) -> ComputeManagementClient:
    return ComputeManagementClient(credential, subscription_id)


def _net_client(subscription_id: str) -> _NetworkClient:
    return _NetworkClient(credential, subscription_id)


def _list_vms(subscription_id: str, resource_group: str) -> str:
    vms = list(_client(subscription_id).virtual_machines.list(resource_group))
    if not vms:
        return f"No VMs found in '{resource_group}'."
    lines = [f"- {vm.name}  size={vm.hardware_profile.vm_size}  location={vm.location}" for vm in vms]
    return "\n".join(lines)


def _get_vm_details(subscription_id: str, resource_group: str, vm_name: str) -> str:
    """Return full VM details including all attached resources."""
    c = _client(subscription_id)
    nc = _net_client(subscription_id)

    vm = c.virtual_machines.get(resource_group, vm_name, expand="instanceView")

    # Power state
    statuses = []
    if vm.instance_view and vm.instance_view.statuses:
        statuses = [s.display_status for s in vm.instance_view.statuses if s.display_status]

    # OS disk
    os_disk = vm.storage_profile.os_disk
    os_disk_name = os_disk.name or "n/a"
    os_disk_size = f"{os_disk.disk_size_gb} GB" if os_disk.disk_size_gb else "n/a"
    os_disk_type = os_disk.managed_disk.storage_account_type if (os_disk.managed_disk and os_disk.managed_disk.storage_account_type) else "n/a"
    os_disk_id = os_disk.managed_disk.id if os_disk.managed_disk else "n/a"

    # Data disks
    data_disk_lines = []
    for d in (vm.storage_profile.data_disks or []):
        disk_type = d.managed_disk.storage_account_type if (d.managed_disk and d.managed_disk.storage_account_type) else "n/a"
        data_disk_lines.append(
            f"  - [{d.lun}] {d.name}  size={d.disk_size_gb or 'n/a'} GB  "
            f"type={disk_type}  caching={d.caching}"
        )

    # Network interfaces — resolve each NIC to get IP config details
    nic_lines = []
    for nic_ref in (vm.network_profile.network_interfaces or []):
        nic_name = nic_ref.id.split("/")[-1]
        nic_rg = nic_ref.id.split("/resourceGroups/")[1].split("/")[0]
        try:
            nic = nc.network_interfaces.get(nic_rg, nic_name)
            for ipc in (nic.ip_configurations or []):
                subnet_name = ipc.subnet.id.split("/")[-1] if ipc.subnet else "n/a"
                vnet_name = ipc.subnet.id.split("/virtualNetworks/")[1].split("/")[0] if ipc.subnet else "n/a"
                private_ip = ipc.private_ip_address or "n/a"

                # Public IP
                public_ip = "none"
                if ipc.public_ip_address:
                    pip_name = ipc.public_ip_address.id.split("/")[-1]
                    pip_rg = ipc.public_ip_address.id.split("/resourceGroups/")[1].split("/")[0]
                    try:
                        pip = nc.public_ip_addresses.get(pip_rg, pip_name)
                        public_ip = pip.ip_address or "unassigned"
                    except Exception:
                        public_ip = pip_name

                # NSG on the NIC
                nsg_name = nic.network_security_group.id.split("/")[-1] if nic.network_security_group else "none"

                nic_lines.append(
                    f"  - {nic_name}  private={private_ip}  public={public_ip}  "
                    f"vnet={vnet_name}  subnet={subnet_name}  nsg={nsg_name}"
                )
        except Exception as exc:
            nic_lines.append(f"  - {nic_name}  [could not resolve: {exc}]")

    # Boot diagnostics
    boot_diag = "disabled"
    if vm.diagnostics_profile and vm.diagnostics_profile.boot_diagnostics:
        bd = vm.diagnostics_profile.boot_diagnostics
        boot_diag = "enabled" if bd.enabled else "disabled"

    lines = [
        f"VM: {vm.name}",
        f"  Status:        {', '.join(statuses) or 'n/a'}",
        f"  Size:          {vm.hardware_profile.vm_size}",
        f"  Location:      {vm.location}",
        f"  OS type:       {vm.storage_profile.os_disk.os_type}",
        f"  Image:         {vm.storage_profile.image_reference.publisher if vm.storage_profile.image_reference else 'custom'} "
                         f"{vm.storage_profile.image_reference.offer if vm.storage_profile.image_reference else ''} "
                         f"{vm.storage_profile.image_reference.sku if vm.storage_profile.image_reference else ''}".strip(),
        f"",
        f"  OS disk:       {os_disk_name}  {os_disk_size}  type={os_disk_type}",
        f"  OS disk ID:    {os_disk_id}",
        f"",
        f"  Data disks ({len(data_disk_lines)}):",
    ] + (data_disk_lines if data_disk_lines else ["  - (none)"]) + [
        f"",
        f"  Network interfaces ({len(nic_lines)}):",
    ] + (nic_lines if nic_lines else ["  - (none)"]) + [
        f"",
        f"  Boot diagnostics: {boot_diag}",
    ]
    return "\n".join(lines)


def _list_vm_disks(subscription_id: str, resource_group: str, vm_name: str) -> str:
    """List all disks attached to a VM with size, type, and encryption details."""
    c = _client(subscription_id)
    vm = c.virtual_machines.get(resource_group, vm_name)

    os_disk = vm.storage_profile.os_disk
    lines = ["OS disk:"]
    os_type = os_disk.managed_disk.storage_account_type if (os_disk.managed_disk and os_disk.managed_disk.storage_account_type) else "n/a"
    os_disk_id = os_disk.managed_disk.id if os_disk.managed_disk else None

    # Fetch full disk object for encryption/IOPS details
    encryption = "n/a"
    iops = "n/a"
    if os_disk_id:
        disk_name = os_disk_id.split("/")[-1]
        try:
            d = c.disks.get(resource_group, disk_name)
            iops = str(d.disk_iops_read_write or "n/a")
            if d.encryption and d.encryption.type:
                encryption = d.encryption.type
        except Exception:
            pass

    lines.append(
        f"  {os_disk.name}  size={os_disk.disk_size_gb or 'n/a'} GB  "
        f"type={os_type}  caching={os_disk.caching}  "
        f"iops={iops}  encryption={encryption}"
    )

    data_disks = vm.storage_profile.data_disks or []
    lines.append(f"\nData disks ({len(data_disks)}):")
    if not data_disks:
        lines.append("  (none)")
    for d in data_disks:
        d_type = d.managed_disk.storage_account_type if (d.managed_disk and d.managed_disk.storage_account_type) else "n/a"
        d_id = d.managed_disk.id if d.managed_disk else None
        d_iops = "n/a"
        d_enc = "n/a"
        if d_id:
            d_disk_name = d_id.split("/")[-1]
            try:
                full = c.disks.get(resource_group, d_disk_name)
                d_iops = str(full.disk_iops_read_write or "n/a")
                if full.encryption and full.encryption.type:
                    d_enc = full.encryption.type
            except Exception:
                pass
        lines.append(
            f"  [{d.lun}] {d.name}  size={d.disk_size_gb or 'n/a'} GB  "
            f"type={d_type}  caching={d.caching}  "
            f"iops={d_iops}  encryption={d_enc}"
        )

    return "\n".join(lines)


def _list_vm_nics(subscription_id: str, resource_group: str, vm_name: str) -> str:
    """List all network interfaces attached to a VM with full IP and NSG details."""
    c = _client(subscription_id)
    nc = _net_client(subscription_id)

    vm = c.virtual_machines.get(resource_group, vm_name)
    nic_refs = vm.network_profile.network_interfaces or []
    if not nic_refs:
        return f"VM '{vm_name}' has no network interfaces."

    lines = []
    for nic_ref in nic_refs:
        nic_name = nic_ref.id.split("/")[-1]
        nic_rg = nic_ref.id.split("/resourceGroups/")[1].split("/")[0]
        primary_marker = " (primary)" if nic_ref.primary else ""
        try:
            nic = nc.network_interfaces.get(nic_rg, nic_name)
            nsg = nic.network_security_group.id.split("/")[-1] if nic.network_security_group else "none"
            accel = getattr(nic, "enable_accelerated_networking", False)
            lines.append(f"NIC: {nic_name}{primary_marker}  NSG={nsg}  accelerated={accel}")

            for ipc in (nic.ip_configurations or []):
                subnet_id = ipc.subnet.id if ipc.subnet else ""
                subnet = subnet_id.split("/")[-1] if subnet_id else "n/a"
                vnet = subnet_id.split("/virtualNetworks/")[1].split("/")[0] if "/virtualNetworks/" in subnet_id else "n/a"
                alloc = ipc.private_ip_allocation_method or "n/a"

                public_ip = "none"
                if ipc.public_ip_address:
                    pip_name = ipc.public_ip_address.id.split("/")[-1]
                    pip_rg = ipc.public_ip_address.id.split("/resourceGroups/")[1].split("/")[0]
                    try:
                        pip = nc.public_ip_addresses.get(pip_rg, pip_name)
                        public_ip = f"{pip.ip_address or 'unassigned'} ({pip.public_ip_allocation_method}  sku={pip.sku.name if pip.sku else 'n/a'})"
                    except Exception:
                        public_ip = pip_name

                lines.append(
                    f"  IP config: {ipc.name}\n"
                    f"    Private IP:  {ipc.private_ip_address or 'n/a'} ({alloc})\n"
                    f"    Public IP:   {public_ip}\n"
                    f"    VNet/Subnet: {vnet} / {subnet}"
                )
        except Exception as exc:
            lines.append(f"NIC: {nic_name}{primary_marker}  [could not resolve: {exc}]")

    return "\n".join(lines)


def _get_vm_status(subscription_id: str, resource_group: str, vm_name: str) -> str:
    iv = _client(subscription_id).virtual_machines.instance_view(resource_group, vm_name)
    statuses = [s.display_status for s in iv.statuses if s.display_status]
    return f"{vm_name}: {', '.join(statuses)}"


def _create_vm(
    subscription_id: str,
    resource_group: str,
    vm_name: str,
    location: str,
    vm_size: str,
    admin_username: str,
    admin_password: str,
    image_publisher: str = "Canonical",
    image_offer: str = "UbuntuServer",
    image_sku: str = "18.04-LTS",
    image_version: str = "latest",
) -> str:
    c = _client(subscription_id)
    network_client = __import__(
        "azure.mgmt.network", fromlist=["NetworkManagementClient"]
    ).NetworkManagementClient(credential, subscription_id)

    # Minimal NIC creation inline — real usage would call the network tools first
    vnet_name = f"{vm_name}-vnet"
    subnet_name = "default"
    nic_name = f"{vm_name}-nic"

    network_client.virtual_networks.begin_create_or_update(
        resource_group, vnet_name,
        {"location": location, "address_space": {"address_prefixes": ["10.0.0.0/16"]}},
    ).result()
    subnet = network_client.subnets.begin_create_or_update(
        resource_group, vnet_name, subnet_name, {"address_prefix": "10.0.0.0/24"}
    ).result()
    nic = network_client.network_interfaces.begin_create_or_update(
        resource_group, nic_name,
        {
            "location": location,
            "ip_configurations": [
                {"name": "ipconfig1", "subnet": {"id": subnet.id}}
            ],
        },
    ).result()

    poller = c.virtual_machines.begin_create_or_update(
        resource_group,
        vm_name,
        {
            "location": location,
            "hardware_profile": {"vm_size": vm_size},
            "storage_profile": {
                "image_reference": {
                    "publisher": image_publisher,
                    "offer": image_offer,
                    "sku": image_sku,
                    "version": image_version,
                },
                "os_disk": {"create_option": "FromImage"},
            },
            "os_profile": {
                "computer_name": vm_name,
                "admin_username": admin_username,
                "admin_password": admin_password,
            },
            "network_profile": {
                "network_interfaces": [{"id": nic.id, "primary": True}]
            },
        },
    )
    vm = poller.result()
    return f"VM '{vm.name}' created in '{resource_group}' ({vm.location}), size={vm.hardware_profile.vm_size}."


def _start_vm(subscription_id: str, resource_group: str, vm_name: str) -> str:
    _client(subscription_id).virtual_machines.begin_start(resource_group, vm_name).result()
    return f"VM '{vm_name}' has been started."


def _stop_vm(subscription_id: str, resource_group: str, vm_name: str) -> str:
    _client(subscription_id).virtual_machines.begin_deallocate(resource_group, vm_name).result()
    return f"VM '{vm_name}' has been stopped (deallocated)."


def _delete_vm(subscription_id: str, resource_group: str, vm_name: str) -> str:
    _client(subscription_id).virtual_machines.begin_delete(resource_group, vm_name).result()
    return f"VM '{vm_name}' has been deleted."


def _list_vm_sizes(subscription_id: str, location: str) -> str:
    sizes = list(_client(subscription_id).virtual_machine_sizes.list(location))
    # Return the most common families to keep output manageable
    lines = [f"- {s.name}  vCPUs={s.number_of_cores}  memoryMB={s.memory_in_mb}" for s in sizes[:40]]
    return "\n".join(lines) + f"\n... ({len(sizes)} total sizes available in {location})"


TOOLS = [
    Tool(
        name="list_virtual_machines",
        description="List all virtual machines in a resource group.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group"],
        },
        func=_list_vms,
    ),
    Tool(
        name="get_vm_status",
        description="Get the power state and provisioning status of a specific VM.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "vm_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "vm_name"],
        },
        func=_get_vm_status,
    ),
    Tool(
        name="create_virtual_machine",
        description=(
            "Create a new virtual machine. Creates a minimal VNet/NIC automatically "
            "if none are specified. For production use, create networking resources first."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "vm_name": {"type": "string"},
                "location": {"type": "string", "description": "Azure region, e.g. eastus."},
                "vm_size": {"type": "string", "description": "e.g. Standard_D2s_v3."},
                "admin_username": {"type": "string"},
                "admin_password": {"type": "string", "description": "Must meet Azure password complexity requirements."},
                "image_publisher": {"type": "string", "default": "Canonical"},
                "image_offer": {"type": "string", "default": "UbuntuServer"},
                "image_sku": {"type": "string", "default": "18.04-LTS"},
                "image_version": {"type": "string", "default": "latest"},
            },
            "required": ["subscription_id", "resource_group", "vm_name", "location", "vm_size", "admin_username", "admin_password"],
        },
        func=_create_vm,
    ),
    Tool(
        name="start_virtual_machine",
        description="Start a stopped (deallocated) virtual machine.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "vm_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "vm_name"],
        },
        func=_start_vm,
    ),
    Tool(
        name="stop_virtual_machine",
        description="Stop (deallocate) a running virtual machine. The VM will no longer incur compute charges.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "vm_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "vm_name"],
        },
        func=_stop_vm,
        destructive=True,
    ),
    Tool(
        name="delete_virtual_machine",
        description="Permanently delete a virtual machine.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "vm_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "vm_name"],
        },
        func=_delete_vm,
        destructive=True,
    ),
    Tool(
        name="get_vm_details",
        description=(
            "Get details for a VM. Use the 'include' parameter to control what is returned: "
            "'all' (default) returns everything — power state, image, OS disk, data disks, "
            "network interfaces, IPs, VNet/subnet, NSGs, boot diagnostics; "
            "'disks' returns only disk details (size, SKU, caching, IOPS, LUN, encryption); "
            "'network' returns only NIC details (private/public IPs, VNet, subnet, NSG, accelerated networking)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "vm_name": {"type": "string"},
                "include": {
                    "type": "string",
                    "enum": ["all", "disks", "network"],
                    "default": "all",
                    "description": "Which attached resources to include in the response.",
                },
            },
            "required": ["subscription_id", "resource_group", "vm_name"],
        },
        func=lambda subscription_id, resource_group, vm_name, include="all": (
            _list_vm_disks(subscription_id, resource_group, vm_name) if include == "disks"
            else _list_vm_nics(subscription_id, resource_group, vm_name) if include == "network"
            else _get_vm_details(subscription_id, resource_group, vm_name)
        ),
    ),
    Tool(
        name="list_vm_sizes",
        description="List available VM sizes in an Azure region.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "location": {"type": "string", "description": "Azure region, e.g. eastus."},
            },
            "required": ["subscription_id", "location"],
        },
        func=_list_vm_sizes,
    ),
]
