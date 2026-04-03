"""Unit tests for tools/resources.py — subscription and resource group operations."""
import pytest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sub(display_name, subscription_id, state="Enabled"):
    return SimpleNamespace(display_name=display_name, subscription_id=subscription_id, state=state)


def _rg(name, location, provisioning_state="Succeeded"):
    props = SimpleNamespace(provisioning_state=provisioning_state)
    return SimpleNamespace(name=name, location=location, properties=props)


def _resource(name, rtype, location):
    return SimpleNamespace(name=name, type=rtype, location=location)


# ---------------------------------------------------------------------------
# _list_subscriptions
# ---------------------------------------------------------------------------

class TestListSubscriptions:
    @patch("tools.resources.SubscriptionClient")
    def test_formats_subscription_lines(self, MockClient):
        MockClient.return_value.subscriptions.list.return_value = [
            _sub("Dev Subscription", "sub-111", "Enabled"),
            _sub("Prod Subscription", "sub-222", "Enabled"),
        ]
        from tools.resources import _list_subscriptions
        result = _list_subscriptions()
        assert "Dev Subscription" in result
        assert "sub-111" in result
        assert "Prod Subscription" in result
        assert "sub-222" in result

    @patch("tools.resources.SubscriptionClient")
    def test_returns_no_subscriptions_message_when_empty(self, MockClient):
        MockClient.return_value.subscriptions.list.return_value = []
        from tools.resources import _list_subscriptions
        result = _list_subscriptions()
        assert "No subscriptions found" in result

    @patch("tools.resources.SubscriptionClient")
    def test_includes_subscription_state(self, MockClient):
        MockClient.return_value.subscriptions.list.return_value = [
            _sub("Dev", "sub-111", "Disabled"),
        ]
        from tools.resources import _list_subscriptions
        result = _list_subscriptions()
        assert "Disabled" in result


# ---------------------------------------------------------------------------
# _list_resource_groups
# ---------------------------------------------------------------------------

class TestListResourceGroups:
    @patch("tools.resources.ResourceManagementClient")
    def test_formats_resource_group_lines(self, MockClient):
        MockClient.return_value.resource_groups.list.return_value = [
            _rg("rg-dev", "eastus"),
            _rg("rg-prod", "westus"),
        ]
        from tools.resources import _list_resource_groups
        result = _list_resource_groups("sub-123")
        assert "rg-dev" in result
        assert "eastus" in result
        assert "rg-prod" in result

    @patch("tools.resources.ResourceManagementClient")
    def test_returns_no_resource_groups_message_when_empty(self, MockClient):
        MockClient.return_value.resource_groups.list.return_value = []
        from tools.resources import _list_resource_groups
        result = _list_resource_groups("sub-123")
        assert "No resource groups found" in result
        assert "sub-123" in result

    @patch("tools.resources.ResourceManagementClient")
    def test_passes_subscription_id_to_client(self, MockClient):
        MockClient.return_value.resource_groups.list.return_value = []
        from tools.resources import _list_resource_groups
        _list_resource_groups("sub-abc")
        MockClient.assert_called_once()
        assert MockClient.call_args[0][1] == "sub-abc"


# ---------------------------------------------------------------------------
# _create_resource_group
# ---------------------------------------------------------------------------

class TestCreateResourceGroup:
    @patch("tools.resources.ResourceManagementClient")
    def test_returns_confirmation_with_rg_name(self, MockClient):
        created_rg = SimpleNamespace(
            name="rg-new",
            location="eastus",
            properties=SimpleNamespace(provisioning_state="Succeeded"),
        )
        MockClient.return_value.resource_groups.create_or_update.return_value = created_rg
        from tools.resources import _create_resource_group
        result = _create_resource_group("sub-123", "rg-new", "eastus")
        assert "rg-new" in result
        assert "Succeeded" in result

    @patch("tools.resources.ResourceManagementClient")
    def test_calls_create_or_update_with_correct_args(self, MockClient):
        created_rg = SimpleNamespace(
            name="rg-test",
            location="westus",
            properties=SimpleNamespace(provisioning_state="Succeeded"),
        )
        MockClient.return_value.resource_groups.create_or_update.return_value = created_rg
        from tools.resources import _create_resource_group
        _create_resource_group("sub-123", "rg-test", "westus")
        MockClient.return_value.resource_groups.create_or_update.assert_called_once_with(
            "rg-test", {"location": "westus"}
        )


# ---------------------------------------------------------------------------
# _delete_resource_group
# ---------------------------------------------------------------------------

class TestDeleteResourceGroup:
    @patch("tools.resources.ResourceManagementClient")
    def test_returns_confirmation_with_rg_name(self, MockClient):
        MockClient.return_value.resource_groups.begin_delete.return_value.result.return_value = None
        from tools.resources import _delete_resource_group
        result = _delete_resource_group("sub-123", "rg-old")
        assert "rg-old" in result
        assert "deleted" in result.lower()

    @patch("tools.resources.ResourceManagementClient")
    def test_calls_begin_delete_and_waits(self, MockClient):
        poller = MagicMock()
        MockClient.return_value.resource_groups.begin_delete.return_value = poller
        from tools.resources import _delete_resource_group
        _delete_resource_group("sub-123", "rg-old")
        MockClient.return_value.resource_groups.begin_delete.assert_called_once_with("rg-old")
        poller.result.assert_called_once()


# ---------------------------------------------------------------------------
# _list_resources
# ---------------------------------------------------------------------------

class TestListResources:
    @patch("tools.resources.ResourceManagementClient")
    def test_formats_resource_lines(self, MockClient):
        MockClient.return_value.resources.list_by_resource_group.return_value = [
            _resource("my-vm", "Microsoft.Compute/virtualMachines", "eastus"),
            _resource("my-sa", "Microsoft.Storage/storageAccounts", "eastus"),
        ]
        from tools.resources import _list_resources
        result = _list_resources("sub-123", "rg-dev")
        assert "my-vm" in result
        assert "Microsoft.Compute/virtualMachines" in result
        assert "my-sa" in result

    @patch("tools.resources.ResourceManagementClient")
    def test_returns_no_resources_message_when_empty(self, MockClient):
        MockClient.return_value.resources.list_by_resource_group.return_value = []
        from tools.resources import _list_resources
        result = _list_resources("sub-123", "rg-empty")
        assert "No resources found" in result
        assert "rg-empty" in result

    @patch("tools.resources.ResourceManagementClient")
    def test_filters_by_resource_group(self, MockClient):
        MockClient.return_value.resources.list_by_resource_group.return_value = []
        from tools.resources import _list_resources
        _list_resources("sub-123", "rg-specific")
        MockClient.return_value.resources.list_by_resource_group.assert_called_once_with("rg-specific")
