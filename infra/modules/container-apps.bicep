param location string

@description('Full resource ID of the user-assigned managed identity.')
param managedIdentityResourceId string

@description('Client ID of the user-assigned managed identity (used as AZURE_MANAGED_IDENTITY_CLIENT_ID).')
param managedIdentityClientId string

param acrLoginServer string

@description('Unversioned Key Vault secret URI for the Anthropic API key.')
param anthropicSecretUri string

@description('Azure subscription ID the agent will manage resources in.')
param agentSubscriptionId string

@description('''
Container image to run. On first deploy this is a hello-world placeholder; the
GitHub Actions workflow updates the image to the real ACR image after pushing it.
''')
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

resource containerAppsEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-azure-agent'
  location: location
  properties: {
    zoneRedundant: false
  }
  tags: {
    application: 'azure-agent'
  }
}

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-azure-agent'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityResourceId}': {}
    }
  }
  tags: {
    application: 'azure-agent'
  }
  properties: {
    managedEnvironmentId: containerAppsEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8080
        // 'auto' supports HTTP/1.1, HTTP/2, and WebSocket upgrades.
        transport: 'auto'
        allowInsecure: false
      }
      // Pull from ACR using the managed identity — no registry credentials stored.
      registries: [
        {
          server: acrLoginServer
          identity: managedIdentityResourceId
        }
      ]
      // Key Vault reference: the managed identity reads the secret at runtime.
      secrets: [
        {
          name: 'anthropic-api-key'
          keyVaultUrl: anthropicSecretUri
          identity: managedIdentityResourceId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'azure-agent'
          image: containerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'ANTHROPIC_API_KEY'
              secretRef: 'anthropic-api-key'
            }
            {
              name: 'AZURE_MANAGED_IDENTITY_CLIENT_ID'
              value: managedIdentityClientId
            }
            {
              name: 'AZURE_DEFAULT_SUBSCRIPTION_ID'
              value: agentSubscriptionId
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

output containerAppName string = containerApp.name
output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
