param location string

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-azure-agent'
  location: location
  tags: {
    application: 'azure-agent'
  }
}

output principalId string = identity.properties.principalId
output clientId string = identity.properties.clientId
output resourceId string = identity.id
