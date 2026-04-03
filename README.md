# azure-agent

azure-agent is a conversational Azure management tool powered by Claude. Instead of navigating the Azure portal or constructing CLI commands, you describe what you want in plain English and the agent figures out the right API calls, asks clarifying questions when needed, and confirms before taking any destructive action.

The agent maintains context across a conversation — once you've told it which subscription or resource group you're working in, you don't need to repeat yourself. It tracks your working context and carries it forward into follow-up requests.

## Capabilities

### Resource Management

Browse and manage the foundational building blocks of your Azure environment.

- List all subscriptions accessible with your credentials
- List, create, and delete resource groups
- List all resources within a resource group

Deleting a resource group is a destructive operation — the agent will state exactly what will be removed and ask for explicit confirmation before proceeding.

### Virtual Machines

Full lifecycle management for Azure VMs.

**Supported:**
- List VMs in a resource group
- Get VM details: power state, OS image, OS disk, data disks (size, SKU, caching, IOPS, LUN, encryption), network interfaces (private/public IPs, VNet, subnet, NSG, accelerated networking)
- List available VM sizes in a region
- Create a VM — automatically provisions a minimal VNet and NIC if none are provided; supports custom image publisher/offer/SKU/version
- Start a deallocated VM
- Stop (deallocate) a running VM — the agent confirms before executing, as this interrupts the workload
- Delete a VM — requires explicit confirmation

**Not supported:**
- Resizing an existing VM
- Attaching or detaching data disks on an existing VM
- Creating or managing VM scale sets
- VM extensions, snapshots, or image capture
- Managed disk operations independent of a VM

### Networking

Manage virtual network infrastructure and inspect security configuration.

**Supported:**
- List virtual networks (VNets) in a resource group
- Create a VNet with a configurable address space (CIDR)
- Delete a VNet (destructive — requires confirmation)
- List network security groups (NSGs) in a resource group
- List and inspect all security rules within an NSG, sorted by priority
- List public IP addresses in a resource group (including SKU and allocation method)

**Not supported:**
- Creating, modifying, or deleting NSGs or individual security rules
- Managing subnets independently
- Route tables, load balancers, application gateways, VPN gateways, or DNS zones
- VNet peering or private endpoints

### Storage

Manage Azure Storage accounts and inspect blob containers.

**Supported:**
- List storage accounts in a resource group (kind, SKU, access tier)
- Create a storage account with configurable SKU (`Standard_LRS`, `Standard_GRS`, `Standard_RAGRS`, `Standard_ZRS`, `Premium_LRS`) and kind (`StorageV2`, `BlobStorage`, `FileStorage`)
- Delete a storage account and all its data (destructive — requires confirmation)
- List blob containers within a storage account, including public access settings

**Not supported:**
- Creating or deleting blob containers
- Uploading, downloading, or managing blobs
- File shares, queues, or tables
- Storage account keys, SAS tokens, or access policies
- Lifecycle management policies or replication configuration

### Azure Kubernetes Service (AKS)

Inspect and manage AKS clusters and node pools.

**Supported:**
- List AKS clusters in a resource group (Kubernetes version, node count)
- Get detailed cluster information including all node pools, SKUs, and configuration
- Scale a node pool to a specified node count — the agent confirms before executing, as this affects running workloads
- Delete a cluster (destructive — requires confirmation)

**Not supported:**
- Creating new AKS clusters
- Adding or removing node pools
- Upgrading Kubernetes versions
- Managing cluster credentials or kubeconfig
- Workload or namespace management within a cluster

### Role-Based Access Control (RBAC)

Inspect and manage Azure RBAC assignments.

**Supported:**
- List role assignments at subscription scope or resource group scope
- List all built-in Azure role definitions available in a subscription
- Create a role assignment — assign any role to a user, group, or service principal at any ARM scope
- Delete a role assignment (destructive — requires confirmation)

**Not supported:**
- Custom role definition management
- Management group scope assignments
- Privileged Identity Management (PIM) / just-in-time access
- Deny assignments

### Azure Policy

Comprehensive policy management covering the full lifecycle from definition to compliance remediation.

**Supported:**
- List policy definitions — filter by `BuiltIn`, `Custom`, or all
- Get full details of a policy definition including its rule logic and parameters
- Create custom policy definitions with a JSON policy rule, configurable mode (`All` or `Indexed`), and parameters
- Delete custom policy definitions (built-in policies cannot be deleted)
- List and inspect policy initiatives (policy sets), including their constituent policies
- List policy assignments at subscription or resource group scope
- Get details of a specific assignment
- Create a policy assignment at any ARM scope, with optional `DoNotEnforce` mode for audit-only evaluation
- Delete a policy assignment (destructive — requires confirmation)
- Get a compliance summary showing non-compliant resource and policy counts
- List non-compliant resources, optionally filtered by policy assignment
- List recent policy evaluation events (audit trail, configurable look-back window)
- List remediation tasks at subscription or resource group scope
- Create a remediation task to bring non-compliant resources into compliance

**Not supported:**
- Exemptions
- Management group scope
- Triggering an on-demand compliance scan

### Microsoft Entra ID

Read-only visibility into your Entra ID (Azure AD) tenant. All Entra operations are read-only — no write, create, or delete operations are available.

**Users:**
- List users with optional name or UPN search
- Get full details for a user: account status, job title, department, last sign-in time
- List a user's group memberships
- List a user's assigned directory roles

**Groups:**
- List groups with optional name search
- Get group details including type and dynamic membership rules
- List group members (users and nested groups)
- List group owners

**App Registrations:**
- List app registrations with client secret and certificate counts
- Get app registration details: redirect URIs, client secrets, certificates
- List API permissions configured for an app

**Service Principals:**
- List enterprise applications with optional name search
- Get service principal details
- List application permissions (app roles) granted to a service principal

**Devices:**
- List registered/joined devices including compliance state and management type

**Directory Roles:**
- List all active directory roles (e.g. Global Administrator, User Administrator)
- List members of a specific directory role

Entra ID access requires either the **Global Reader** directory role (for interactive user accounts) or Graph API application permissions (`User.Read.All`, `Group.Read.All`, `Application.Read.All`, `Device.Read.All`, `RoleManagement.Read.Directory`) for service principals. See [app/ENTRA_SETUP.md](app/ENTRA_SETUP.md) for setup instructions.

---

## Safety

Before executing any destructive operation — deleting resources, stopping VMs, scaling down node pools, removing role assignments — the agent will describe exactly what will be affected and require unambiguous confirmation. It will not proceed if the confirmation is unclear or absent.

---

## Installation

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- An [Anthropic API key](https://console.anthropic.com/)
- Azure credentials — `az login`, a service principal, or a managed identity

### Setup

**1. Configure the agent**

```bash
cp app/.azure-agent.example app/.azure-agent
```

Edit `app/.azure-agent` and set your Anthropic API key:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Optionally set a default subscription so the agent doesn't ask every time:

```
AZURE_DEFAULT_SUBSCRIPTION_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

**2. Authenticate with Azure**

The recommended approach is to log in with the Azure CLI on your host. Your credentials will be mounted into the container automatically.

```bash
az login
```

Alternatively, authenticate using a **service principal**:

```
AZURE_TENANT_ID=...
AZURE_CLIENT_ID=...
AZURE_CLIENT_SECRET=...
```

Or use a **managed identity** when running on an Azure resource (VM, Container App, etc.):

```
# System-assigned
AZURE_USE_MANAGED_IDENTITY=true

# User-assigned (set the client ID of the identity)
AZURE_MANAGED_IDENTITY_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

**3. Build and run**

```bash
docker compose up --build
```

Then open [http://localhost:8080](http://localhost:8080) in your browser.

### Running locally (without Docker)

```bash
cd app
pip install -r requirements.txt
python azure-agent.py
```
