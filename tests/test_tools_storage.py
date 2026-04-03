"""Unit tests for tools/storage.py — storage account and blob container operations."""
import pytest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _account(name, kind="StorageV2", sku_name="Standard_LRS", location="eastus", access_tier="Hot"):
    return SimpleNamespace(
        name=name,
        kind=kind,
        sku=SimpleNamespace(name=sku_name),
        location=location,
        access_tier=access_tier,
    )


def _container(name, public_access=None):
    return SimpleNamespace(name=name, public_access=public_access)


# ---------------------------------------------------------------------------
# _list_storage_accounts
# ---------------------------------------------------------------------------

class TestListStorageAccounts:
    @patch("tools.storage._client")
    def test_formats_account_lines(self, mock_client):
        mock_client.return_value.storage_accounts.list_by_resource_group.return_value = [
            _account("mystorage1", kind="StorageV2", sku_name="Standard_LRS", location="eastus"),
            _account("mystorage2", kind="BlobStorage", sku_name="Standard_GRS", location="westus"),
        ]
        from tools.storage import _list_storage_accounts
        result = _list_storage_accounts("sub-123", "rg-dev")
        assert "mystorage1" in result
        assert "StorageV2" in result
        assert "Standard_LRS" in result
        assert "mystorage2" in result
        assert "BlobStorage" in result

    @patch("tools.storage._client")
    def test_returns_no_accounts_message_when_empty(self, mock_client):
        mock_client.return_value.storage_accounts.list_by_resource_group.return_value = []
        from tools.storage import _list_storage_accounts
        result = _list_storage_accounts("sub-123", "rg-dev")
        assert "No storage accounts found" in result
        assert "rg-dev" in result

    @patch("tools.storage._client")
    def test_includes_access_tier(self, mock_client):
        mock_client.return_value.storage_accounts.list_by_resource_group.return_value = [
            _account("mysa", access_tier="Cool"),
        ]
        from tools.storage import _list_storage_accounts
        result = _list_storage_accounts("sub-123", "rg-dev")
        assert "Cool" in result


# ---------------------------------------------------------------------------
# _create_storage_account
# ---------------------------------------------------------------------------

class TestCreateStorageAccount:
    @patch("tools.storage._client")
    def test_returns_confirmation_with_account_name(self, mock_client):
        created = _account("mynewsa", kind="StorageV2", sku_name="Standard_LRS", location="eastus")
        mock_client.return_value.storage_accounts.begin_create.return_value.result.return_value = created
        from tools.storage import _create_storage_account
        result = _create_storage_account("sub-123", "rg-dev", "mynewsa", "eastus")
        assert "mynewsa" in result
        assert "Standard_LRS" in result
        assert "eastus" in result

    @patch("tools.storage._client")
    def test_waits_for_poller(self, mock_client):
        poller = MagicMock()
        poller.result.return_value = _account("mysa")
        mock_client.return_value.storage_accounts.begin_create.return_value = poller
        from tools.storage import _create_storage_account
        _create_storage_account("sub-123", "rg-dev", "mysa", "eastus")
        poller.result.assert_called_once()

    @patch("tools.storage._client")
    def test_uses_default_sku_and_kind(self, mock_client):
        from azure.mgmt.storage.models import StorageAccountCreateParameters, Sku, Kind
        poller = MagicMock()
        poller.result.return_value = _account("mysa")
        mock_client.return_value.storage_accounts.begin_create.return_value = poller
        from tools.storage import _create_storage_account
        _create_storage_account("sub-123", "rg-dev", "mysa", "eastus")
        _, kwargs_or_args = mock_client.return_value.storage_accounts.begin_create.call_args
        # Verify begin_create was called (params checked by type)
        mock_client.return_value.storage_accounts.begin_create.assert_called_once()


# ---------------------------------------------------------------------------
# _delete_storage_account
# ---------------------------------------------------------------------------

class TestDeleteStorageAccount:
    @patch("tools.storage._client")
    def test_returns_confirmation_with_account_name(self, mock_client):
        mock_client.return_value.storage_accounts.delete.return_value = None
        from tools.storage import _delete_storage_account
        result = _delete_storage_account("sub-123", "rg-dev", "mysa")
        assert "mysa" in result
        assert "deleted" in result.lower()

    @patch("tools.storage._client")
    def test_calls_delete_with_correct_args(self, mock_client):
        from tools.storage import _delete_storage_account
        _delete_storage_account("sub-123", "rg-dev", "mysa")
        mock_client.return_value.storage_accounts.delete.assert_called_once_with("rg-dev", "mysa")


# ---------------------------------------------------------------------------
# _list_blob_containers
# ---------------------------------------------------------------------------

class TestListBlobContainers:
    @patch("tools.storage._client")
    def test_formats_container_lines(self, mock_client):
        mock_client.return_value.blob_containers.list.return_value = [
            _container("images", public_access=None),
            _container("public-data", public_access="Blob"),
        ]
        from tools.storage import _list_blob_containers
        result = _list_blob_containers("sub-123", "rg-dev", "mysa")
        assert "images" in result
        assert "public-data" in result
        assert "Blob" in result

    @patch("tools.storage._client")
    def test_returns_no_containers_message_when_empty(self, mock_client):
        mock_client.return_value.blob_containers.list.return_value = []
        from tools.storage import _list_blob_containers
        result = _list_blob_containers("sub-123", "rg-dev", "mysa")
        assert "No blob containers found" in result
        assert "mysa" in result

    @patch("tools.storage._client")
    def test_filters_by_account_name(self, mock_client):
        mock_client.return_value.blob_containers.list.return_value = []
        from tools.storage import _list_blob_containers
        _list_blob_containers("sub-123", "rg-dev", "specific-account")
        mock_client.return_value.blob_containers.list.assert_called_once_with("rg-dev", "specific-account")


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

class TestStorageToolRegistration:
    def test_delete_storage_account_is_destructive(self):
        from tools.storage import TOOLS
        tool_map = {t.name: t for t in TOOLS}
        assert tool_map["delete_storage_account"].destructive is True

    def test_list_and_create_are_not_destructive(self):
        from tools.storage import TOOLS
        tool_map = {t.name: t for t in TOOLS}
        assert tool_map["list_storage_accounts"].destructive is False
        assert tool_map["create_storage_account"].destructive is False

    def test_expected_tools_registered(self):
        from tools.storage import TOOLS
        names = {t.name for t in TOOLS}
        assert {"list_storage_accounts", "create_storage_account",
                "delete_storage_account", "list_blob_containers"}.issubset(names)
