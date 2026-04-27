terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.14"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
  backend "azurerm" {
    resource_group_name  = "RG-Archive"
    storage_account_name = "kpnarchive"
    container_name       = "tfstate"
    key                  = "azure-agent-ai/terraform.tfstate"
  }  
}

provider "azurerm" {
  features {
    key_vault {
      # Retain key vaults on destroy to prevent accidental data loss.
      # Set to true if you want terraform destroy to fully clean up.
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
}
