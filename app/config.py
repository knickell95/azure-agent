import os
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

# AI provider — "anthropic" (default) or "openai"
AI_PROVIDER = os.getenv("AI_PROVIDER", "anthropic")

# OpenAI / Azure OpenAI settings (used when AI_PROVIDER=openai)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
OPENAI_API_VERSION = os.getenv("OPENAI_API_VERSION", "")
OPENAI_DEPLOYMENT_NAME = os.getenv("OPENAI_DEPLOYMENT_NAME", "")


def _build_credential():
    """Return the appropriate credential based on environment configuration.

    Priority:
    1. User-assigned managed identity — when AZURE_MANAGED_IDENTITY_CLIENT_ID is set
    2. System-assigned managed identity — when AZURE_USE_MANAGED_IDENTITY=true
    3. DefaultAzureCredential — covers service principal env vars, az CLI, etc.
    """
    client_id = os.getenv("AZURE_MANAGED_IDENTITY_CLIENT_ID")
    if client_id:
        return ManagedIdentityCredential(client_id=client_id)

    if os.getenv("AZURE_USE_MANAGED_IDENTITY", "").lower() == "true":
        return ManagedIdentityCredential()

    return DefaultAzureCredential()


# Single credential instance shared across all SDK clients
credential = _build_credential()

# Optional default subscription — agents will ask if not set
DEFAULT_SUBSCRIPTION_ID = os.getenv("AZURE_DEFAULT_SUBSCRIPTION_ID", "")
