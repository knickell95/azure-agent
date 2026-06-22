using 'main.bicep'

// Region — must match a region that supports Azure Container Apps.
// Run: az provider list --query "[?namespace=='Microsoft.App'].registrationState"
param location = 'westus2'

param resourceGroupName = 'rg-azure-agent'

// acrName and keyVaultName use uniqueString defaults; they are stable across
// deployments to the same subscription, so no need to set them unless you want
// custom names.

// deployerObjectId and anthropicApiKey are injected by the GitHub Actions
// workflow and are not set here.
