# ---------------------------------------------------------------------------
# Azure OpenAI account
# ---------------------------------------------------------------------------

resource "azurerm_cognitive_account" "openai" {
  name                = "${var.openai_account_name}-${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  kind                = "OpenAI"
  sku_name            = "S0"

  # Restrict public access. Remove or adjust if you need access from
  # specific networks only (set network_acls instead).
  public_network_access_enabled = true

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags
}

# Allow the Hub project's managed identity to call the OpenAI account
# without an API key (useful when running on an Azure-hosted resource).
resource "azurerm_role_assignment" "project_openai" {
  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_ai_foundry_project.main.identity[0].principal_id
}

# ---------------------------------------------------------------------------
# Model deployment
# ---------------------------------------------------------------------------

resource "azurerm_cognitive_deployment" "model" {
  name                 = var.model_name
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = var.model_name
    version = var.model_version != "" ? var.model_version : null
  }

  sku {
    name     = var.model_sku
    capacity = var.model_capacity
  }
}
