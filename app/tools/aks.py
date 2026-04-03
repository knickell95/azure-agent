"""Tools for Azure Kubernetes Service (AKS) clusters."""
from azure.mgmt.containerservice import ContainerServiceClient
from azure.mgmt.containerservice.models import ManagedCluster, ManagedClusterAgentPoolProfile
from config import credential
from tools.base import Tool


def _client(subscription_id: str) -> ContainerServiceClient:
    return ContainerServiceClient(credential, subscription_id)


def _list_clusters(subscription_id: str, resource_group: str) -> str:
    clusters = list(_client(subscription_id).managed_clusters.list_by_resource_group(resource_group))
    if not clusters:
        return f"No AKS clusters found in '{resource_group}'."
    lines = [
        f"- {c.name}  k8s={c.kubernetes_version}  nodes={sum(p.count or 0 for p in (c.agent_pool_profiles or []))}  "
        f"state={c.provisioning_state}  location={c.location}"
        for c in clusters
    ]
    return "\n".join(lines)


def _get_cluster(subscription_id: str, resource_group: str, cluster_name: str) -> str:
    c = _client(subscription_id).managed_clusters.get(resource_group, cluster_name)
    pools = "\n".join(
        f"  - pool '{p.name}'  count={p.count}  vm={p.vm_size}  mode={p.mode}"
        for p in (c.agent_pool_profiles or [])
    )
    return (
        f"Cluster: {c.name}\n"
        f"  State: {c.provisioning_state}\n"
        f"  Kubernetes: {c.kubernetes_version}\n"
        f"  Location: {c.location}\n"
        f"  FQDN: {c.fqdn}\n"
        f"  Node pools:\n{pools}"
    )


def _scale_node_pool(
    subscription_id: str,
    resource_group: str,
    cluster_name: str,
    node_pool_name: str,
    node_count: int,
) -> str:
    c = _client(subscription_id)
    poller = c.agent_pools.begin_create_or_update(
        resource_group,
        cluster_name,
        node_pool_name,
        {"count": node_count},
    )
    pool = poller.result()
    return f"Node pool '{pool.name}' in cluster '{cluster_name}' scaled to {pool.count} nodes."


def _delete_cluster(subscription_id: str, resource_group: str, cluster_name: str) -> str:
    _client(subscription_id).managed_clusters.begin_delete(resource_group, cluster_name).result()
    return f"AKS cluster '{cluster_name}' has been deleted."


TOOLS = [
    Tool(
        name="list_aks_clusters",
        description="List all AKS clusters in a resource group.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group"],
        },
        func=_list_clusters,
    ),
    Tool(
        name="get_aks_cluster",
        description="Get detailed information about a specific AKS cluster including node pools.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "cluster_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "cluster_name"],
        },
        func=_get_cluster,
    ),
    Tool(
        name="scale_aks_node_pool",
        description="Change the node count for a specific node pool in an AKS cluster.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "cluster_name": {"type": "string"},
                "node_pool_name": {"type": "string"},
                "node_count": {"type": "integer", "minimum": 0},
            },
            "required": ["subscription_id", "resource_group", "cluster_name", "node_pool_name", "node_count"],
        },
        func=_scale_node_pool,
        destructive=True,
    ),
    Tool(
        name="delete_aks_cluster",
        description="Permanently delete an AKS cluster.",
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "cluster_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "cluster_name"],
        },
        func=_delete_cluster,
        destructive=True,
    ),
]
