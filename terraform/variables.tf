variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "westus2"
}

variable "resource_group_name" {
  description = "Name of the resource group to create."
  type        = string
  default     = "rg-azure-agent-ai"
}

variable "hub_name" {
  description = "Name of the Azure AI Foundry Hub."
  type        = string
  default     = "azure-agent-hub"
}

variable "project_name" {
  description = "Name of the Azure AI Foundry Project within the Hub."
  type        = string
  default     = "azure-agent-project"
}

variable "openai_account_name" {
  description = "Base name for the Azure OpenAI account. A random suffix is appended to ensure global uniqueness."
  type        = string
  default     = "oai-azure-agent"
}

variable "model_name" {
  description = "The OpenAI model to deploy, e.g. gpt-4o, gpt-4o-mini, gpt-5.2."
  type        = string
  default     = "gpt-5.2"
}

variable "model_version" {
  description = "Version of the model to deploy. Check available versions in your region via 'az cognitiveservices account list-models'."
  type        = string
  default     = ""
}

variable "model_capacity" {
  description = "Throughput quota for the deployment in thousands of tokens per minute (PTU or TPM depending on sku)."
  type        = number
  default     = 10
}

variable "model_sku" {
  description = "Deployment SKU. GlobalStandard is pay-as-you-go; ProvisionedManaged requires quota approval."
  type        = string
  default     = "GlobalStandard"

  validation {
    condition     = contains(["GlobalStandard", "Standard", "ProvisionedManaged"], var.model_sku)
    error_message = "model_sku must be one of: GlobalStandard, Standard, ProvisionedManaged."
  }
}

variable "tags" {
  description = "Tags applied to all resources."
  type        = map(string)
  default = {
    application = "azure-agent"
    managed-by  = "terraform"
  }
}
