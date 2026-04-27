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
- Create an NSG
- Delete an NSG (destructive — requires confirmation)
- Create or update a security rule on an NSG (priority, direction, access, protocol, source/destination address and port)
- Delete a security rule from an NSG (destructive — requires confirmation)
- List public IP addresses in a resource group (including SKU and allocation method)

**Not supported:**
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
- Create a policy assignment at any ARM scope, with optional `DoNotEnforce` mode for audit-only evaluation; supports attaching a system-assigned or user-assigned managed identity (required for `deployIfNotExists` and `modify` policy effects)
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

### Managed Identities

Create and manage user-assigned managed identities.

**Supported:**
- List all user-assigned managed identities in a resource group
- Get full details of an identity — resource ID, client ID, principal ID, and tenant ID
- Create a user-assigned managed identity
- Update tags on an identity
- Delete an identity (destructive — requires confirmation)
- List all Azure resources currently using an identity (useful before deleting)

**Not supported:**
- System-assigned managed identities (these are managed through the resource they are attached to, e.g. a VM or Container App)
- Federated identity credentials

**Required role:** `Managed Identity Contributor` for write and delete operations; `Managed Identity Operator` to read and assign existing identities to resources.

### Azure Monitor — Diagnostic Settings

Configure and manage diagnostic settings on any Azure resource to route logs and metrics to a destination of your choice.

**Supported:**
- List all diagnostic settings on a resource (destination summary, log and metric category counts)
- Get full details of a diagnostic setting (all log/metric categories, enabled state, retention policy, destinations)
- Create or update a diagnostic setting — supports Log Analytics workspace, storage account, and Event Hub destinations; enable all log categories at once with `allLogs` or specify individual categories; configurable per-destination retention
- Delete a diagnostic setting (destructive — requires confirmation)

**Not supported:**
- Querying log data or running Log Analytics queries
- Managing Log Analytics workspaces or Event Hub namespaces
- Activity log export settings (subscription-level diagnostic settings)
- Azure Monitor alerts, action groups, or metric alert rules

**Required role:** `Monitoring Contributor` for write operations; `Monitoring Reader` for read-only operations.

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

## Required Azure Permissions

The agent uses whichever credentials are configured in `.azure-agent` (az CLI login, service principal, or managed identity). The minimum Azure RBAC roles required depend on which operations you intend to perform.

**Reader** at subscription scope is sufficient for all listing and inspection operations across every service area. Write and destructive operations require the additional roles shown below.

| Service area | Read-only operations | Write / destructive operations |
|---|---|---|
| Resource Management | Reader | Contributor |
| Virtual Machines | Reader | Virtual Machine Contributor ¹ |
| Networking | Reader | Network Contributor |
| Storage | Reader | Storage Account Contributor |
| AKS | Reader | Azure Kubernetes Service Contributor Role |
| RBAC | Reader | User Access Administrator |
| Policy | Reader | Resource Policy Contributor ² |
| Managed Identities | Managed Identity Operator | Managed Identity Contributor |
| Azure Monitor | Monitoring Reader | Monitoring Contributor |
| Entra ID | Global Reader (directory role) ³ | — (read-only) |

**¹ Virtual Machine Contributor + Network Contributor** — VM creation automatically provisions a VNet and NIC when none are provided, which requires network write permissions in addition to the VM Contributor role. If networking resources already exist, Virtual Machine Contributor alone is sufficient.

**² Resource Policy Contributor** covers creating and deleting policy definitions, initiatives, and assignments, and creating remediation tasks. Viewing compliance results and evaluation events requires only Reader.

**³ Entra ID** uses the Microsoft Graph API rather than ARM. Interactive user accounts need the **Global Reader** directory role. Service principals need the Graph API application permissions `User.Read.All`, `Group.Read.All`, `Application.Read.All`, `Device.Read.All`, and `RoleManagement.Read.Directory`. See [app/ENTRA_SETUP.md](app/ENTRA_SETUP.md) for setup instructions.

### Simplified role assignment

If you prefer to assign a single role rather than per-service roles:

- **Contributor** at subscription scope covers all write operations except RBAC role assignments.
- **Contributor + User Access Administrator** covers everything except Entra ID.
- **Owner** at subscription scope covers all ARM operations including role assignments, but grants broader permissions than necessary for most use cases.

Roles can be assigned at subscription scope (access to all resource groups) or narrowed to a specific resource group scope (restricts the agent to that resource group only).

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

### Deploying a model with Terraform

The `terraform/` directory contains configuration to deploy an **Azure AI Foundry Hub and Project** with an **Azure OpenAI model deployment** (default: `gpt-4o`).

**Resources created:**
- Resource group
- Storage account and Key Vault (required by AI Foundry Hub)
- Azure AI Foundry Hub and Project
- Azure OpenAI account with a model deployment
- Connection between the OpenAI account and the Hub (visible in the AI Foundry portal)
- RBAC role assignments for managed identities

**Deploy:**

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars to set your preferred region and model
terraform init
terraform apply
```

**Configure the app** after a successful apply:

```bash
terraform output -raw app_env_vars >> ../app/.azure-agent
```

This appends the `AI_PROVIDER`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_API_VERSION`, and `OPENAI_DEPLOYMENT_NAME` variables directly to your config file.

**Required permissions to deploy:** the principal running `terraform apply` needs `Contributor` + `User Access Administrator` on the target subscription (or a custom role with `Microsoft.Authorization/roleAssignments/write`), as the configuration creates RBAC role assignments.

### Running locally (without Docker)

```bash
cd app
pip install -r requirements.txt
python azure-agent.py
```
