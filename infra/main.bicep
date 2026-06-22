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

// ── Outputs ─────────────────────────────────────────────────────────────────

output resourceGroupName string = resourceGroupName
output acrName string = acr.outputs.acrName
output acrLoginServer string = acr.outputs.loginServer
output containerAppName string = containerApps.outputs.containerAppName
output containerAppUrl string = 'https://${containerApps.outputs.containerAppFqdn}'
output managedIdentityPrincipalId string = identity.outputs.principalId
