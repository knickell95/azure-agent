targetScope = 'subscription'

@description('Azure region for all resources.')
param location string = 'westus2'

@description('Resource group name.')
param resourceGroupName string = 'rg-azure-agent'

@description('Container Registry name. Must be globally unique, 5-50 alphanumeric characters, no hyphens.')
param acrName string = 'cracazureagent${take(uniqueString(subscription().subscriptionId), 8)}'

@description('Key Vault name. Must be globally unique, 3-24 alphanumeric and hyphen characters.')
param keyVaultName string = 'kv-az-agent-${take(uniqueString(subscription().subscriptionId), 6)}'

@description('Object ID of the GitHub Actions service principal used to deploy this template.')
param deployerObjectId string

@secure()
@description('Anthropic API key — stored in Key Vault and injected into the Container App at runtime.')
param anthropicApiKey string

@description('Azure subscription ID the agent will manage. Defaults to the deployment subscription.')
param agentSubscriptionId string = subscription().subscriptionId

// ── Resource Group ──────────────────────────────────────────────────────────

resource rg 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name: resourceGroupName
  location: location
  tags: {
    application: 'azure-agent'
    'managed-by': 'bicep'
  }
}

// ── Managed Identity ────────────────────────────────────────────────────────

module identity 'modules/identity.bicep' = {
  name: 'identity'
  scope: rg
  params: {
    location: location
  }
}

// ── Container Registry ──────────────────────────────────────────────────────

module acr 'modules/acr.bicep' = {
  name: 'acr'
  scope: rg
  params: {
    acrName: acrName
    location: location
    pullPrincipalId: identity.outputs.principalId
  }
}

// ── Key Vault ───────────────────────────────────────────────────────────────

module keyVault 'modules/keyvault.bicep' = {
  name: 'keyVault'
  scope: rg
  params: {
    keyVaultName: keyVaultName
    location: location
    readerObjectId: identity.outputs.principalId
    deployerObjectId: deployerObjectId
    anthropicApiKey: anthropicApiKey
  }
}

// ── Container Apps ──────────────────────────────────────────────────────────

module containerApps 'modules/container-apps.bicep' = {
  name: 'containerApps'
  scope: rg
  params: {
    location: location
    managedIdentityResourceId: identity.outputs.resourceId
    managedIdentityClientId: identity.outputs.clientId
    acrLoginServer: acr.outputs.loginServer
    anthropicSecretUri: keyVault.outputs.anthropicSecretUri
    agentSubscriptionId: agentSubscriptionId
  }
}

// ── Agent Azure Permissions ─────────────────────────────────────────────────
// Grant the Container App's managed identity Contributor on this subscription
// so the agent can manage Azure resources on your behalf.
//
// Scope this down to specific resource groups if you want to limit blast radius,
// or use a custom role if you need read-only access for some tool categories.
//
// Note: the identity.py and entra.py tools may need additional permissions
// (User Access Administrator, Directory Reader) configured separately.

resource agentContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  // Use stable, start-time-calculable inputs for the name so Bicep can resolve it
  // before modules complete. The principalId is used only in properties, which is fine.
  name: guid(subscription().id, resourceGroupName, 'id-azure-agent', 'contributor')
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'b24988ac-6180-42a0-ab88-20f7382dd24c' // Contributor
    )
    principalId: identity.outputs.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Outputs ─────────────────────────────────────────────────────────────────

output resourceGroupName string = resourceGroupName
output acrName string = acr.outputs.acrName
output acrLoginServer string = acr.outputs.loginServer
output containerAppName string = containerApps.outputs.containerAppName
output containerAppUrl string = 'https://${containerApps.outputs.containerAppFqdn}'
output managedIdentityPrincipalId string = identity.outputs.principalId
