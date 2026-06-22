param acrName string
param location string

@description('Principal ID of the managed identity that will pull images (AcrPull).')
param pullPrincipalId string

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: acrName
  location: location
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
  tags: {
    application: 'azure-agent'
  }
}

// Allow the Container App managed identity to pull images without admin credentials.
resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, pullPrincipalId, 'acrpull')
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d' // AcrPull
    )
    principalId: pullPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output loginServer string = acr.properties.loginServer
output acrName string = acr.name
