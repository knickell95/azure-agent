import os
from azure.identity import DefaultAzureCredential

# Single credential instance shared across all SDK clients
credential = DefaultAzureCredential()

# Optional default subscription — agents will ask if not set
DEFAULT_SUBSCRIPTION_ID = os.getenv("AZURE_DEFAULT_SUBSCRIPTION_ID", "")
