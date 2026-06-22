param keyVaultName string
param location string

@description('Object ID of the managed identity that will read Key Vault secrets (get, list).')
param readerObjectId string

@description('Object ID of the GitHub Actions service principal that will write secrets during deployment.')
param deployerObjectId string

@secure()
param anthropicApiKey string

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    // Access policies let us grant the managed identity read access and the deployer
    // write access without the RBAC propagation delay that RBAC authorization incurs.
    enableRbacAuthorization: false
    accessPolicies: [
      {
        tenantId: subscription().tenantId
        objectId: readerObjectId
        permissions: {
          secrets: ['get', 'list']
        }
      }
      {
        tenantId: subscription().tenantId
        objectId: deployerObjectId
        permissions: {
          secrets: ['get', 'set', 'list', 'delete', 'purge']
        }
      }
    ]
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: true // Irreversible once set; matches existing vault state
    publicNetworkAccess: 'Enabled'
  }
  tags: {
    application: 'azure-agent'
  }
}

resource anthropicSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'anthropic-api-key'
  properties: {
    value: anthropicApiKey
  }
}

// Unversioned URI — Container Apps will always fetch the latest active version.
output vaultUri string = keyVault.properties.vaultUri
output anthropicSecretUri string = '${keyVault.properties.vaultUri}secrets/${anthropicSecret.name}'
