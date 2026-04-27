# ---------------------------------------------------------------------------
# Supporting infrastructure required by the AI Foundry Hub
# ---------------------------------------------------------------------------

resource "azurerm_storage_account" "main" {
  name                     = "stazagent${random_string.suffix.result}"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  # Required by AI Foundry Hub
  is_hns_enabled = false

  tags = var.tags
}

resource "azurerm_key_vault" "main" {
  name                = "kv-azagent-${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  # Soft-delete and purge protection are required by AI Foundry Hub.
  soft_delete_retention_days = 7
  purge_protection_enabled   = true

  # Use Azure RBAC for access control rather than legacy access policies.
  rbac_authorization_enabled = true

  tags = var.tags
}

# Allow the Hub's managed identity to manage secrets in the Key Vault.
resource "azurerm_role_assignment" "hub_kv_secrets" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = azurerm_ai_foundry.hub.identity[0].principal_id
}

# Allow the Hub's managed identity to read/write blobs in the storage account.
resource "azurerm_role_assignment" "hub_storage_blob" {
  scope                = azurerm_storage_account.main.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_ai_foundry.hub.identity[0].principal_id
}

# Allow the deploying principal to manage secrets (needed during terraform apply).
resource "azurerm_role_assignment" "deployer_kv_secrets" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

# ---------------------------------------------------------------------------
# Azure AI Foundry Hub
# ---------------------------------------------------------------------------

resource "azurerm_ai_foundry" "hub" {
  name                = var.hub_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  storage_account_id  = azurerm_storage_account.main.id
  key_vault_id        = azurerm_key_vault.main.id

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Azure AI Foundry Project
# ---------------------------------------------------------------------------

resource "azurerm_ai_foundry_project" "main" {
  name               = var.project_name
  location           = azurerm_ai_foundry.hub.location
  ai_services_hub_id = azurerm_ai_foundry.hub.id

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags
}

# NOTE: Linking the OpenAI account to the Hub as a named connection (so
# deployed models appear under the project in the AI Foundry portal) is not
# yet supported by the azurerm provider. Add the connection manually after
# apply via: AI Foundry portal → your project → Management → Connected resources
# → New connection → Azure OpenAI → select the account created above.
