
# Used to scope role assignments to the deploying principal's tenant.
data "azurerm_client_config" "current" {}

# Random suffix for globally unique resource names (storage, key vault, openai).
resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location

  tags = var.tags
}
