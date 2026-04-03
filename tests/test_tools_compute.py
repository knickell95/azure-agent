"""Unit tests for tools/compute.py — virtual machine operations."""
import pytest
from unittest.mock import MagicMock, patch, call
from types import SimpleNamespace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vm(name, size="Standard_D2s_v3", location="eastus"):
    return SimpleNamespace(
        name=name,
        hardware_profile=SimpleNamespace(vm_size=size),
        location=location,
    )


def _vm_size(name, cores=2, memory_mb=8192):
    return SimpleNamespace(name=name, number_of_cores=cores, memory_in_mb=memory_mb)


def _instance_view(*statuses):
    return SimpleNamespace(
        statuses=[SimpleNamespace(display_status=s) for s in statuses]
    )


# ---------------------------------------------------------------------------
# _list_vms
# ---------------------------------------------------------------------------

class TestListVMs:
    @patch("tools.compute._client")
    def test_formats_vm_lines(self, mock_client):
        mock_client.return_value.virtual_machines.list.return_value = [
            _vm("vm-1", "Standard_D2s_v3", "eastus"),
            _vm("vm-2", "Standard_B1s", "westus"),
        ]
        from tools.compute import _list_vms
        result = _list_vms("sub-123", "rg-dev")
        assert "vm-1" in result
        assert "Standard_D2s_v3" in result
        assert "vm-2" in result
        assert "Standard_B1s" in result

    @patch("tools.compute._client")
    def test_returns_no_vms_message_when_empty(self, mock_client):
        mock_client.return_value.virtual_machines.list.return_value = []
        from tools.compute import _list_vms
        result = _list_vms("sub-123", "rg-dev")
        assert "No VMs found" in result
        assert "rg-dev" in result

    @patch("tools.compute._client")
    def test_includes_location_in_output(self, mock_client):
        mock_client.return_value.virtual_machines.list.return_value = [
            _vm("my-vm", location="southcentralus"),
        ]
        from tools.compute import _list_vms
        result = _list_vms("sub-123", "rg-dev")
        assert "southcentralus" in result


# ---------------------------------------------------------------------------
# _get_vm_status
# ---------------------------------------------------------------------------

class TestGetVMStatus:
    @patch("tools.compute._client")
    def test_returns_vm_name_and_statuses(self, mock_client):
        mock_client.return_value.virtual_machines.instance_view.return_value = _instance_view(
            "VM running", "Provisioning succeeded"
        )
        from tools.compute import _get_vm_status
        result = _get_vm_status("sub-123", "rg-dev", "my-vm")
        assert "my-vm" in result
        assert "VM running" in result
        assert "Provisioning succeeded" in result

    @patch("tools.compute._client")
    def test_filters_out_empty_status_strings(self, mock_client):
        mock_client.return_value.virtual_machines.instance_view.return_value = SimpleNamespace(
            statuses=[
                SimpleNamespace(display_status="VM running"),
                SimpleNamespace(display_status=None),
                SimpleNamespace(display_status=""),
            ]
        )
        from tools.compute import _get_vm_status
        result = _get_vm_status("sub-123", "rg-dev", "my-vm")
        assert "VM running" in result
        # None/empty should not appear in output
        assert "None" not in result


# ---------------------------------------------------------------------------
# _start_vm / _stop_vm / _delete_vm
# ---------------------------------------------------------------------------

class TestVMLifecycle:
    @patch("tools.compute._client")
    def test_start_vm_returns_confirmation(self, mock_client):
        mock_client.return_value.virtual_machines.begin_start.return_value.result.return_value = None
        from tools.compute import _start_vm
        result = _start_vm("sub-123", "rg-dev", "my-vm")
        assert "my-vm" in result
        assert "started" in result.lower()

    @patch("tools.compute._client")
    def test_start_vm_waits_for_completion(self, mock_client):
        poller = MagicMock()
        mock_client.return_value.virtual_machines.begin_start.return_value = poller
        from tools.compute import _start_vm
        _start_vm("sub-123", "rg-dev", "my-vm")
        mock_client.return_value.virtual_machines.begin_start.assert_called_once_with("rg-dev", "my-vm")
        poller.result.assert_called_once()

    @patch("tools.compute._client")
    def test_stop_vm_returns_confirmation(self, mock_client):
        mock_client.return_value.virtual_machines.begin_deallocate.return_value.result.return_value = None
        from tools.compute import _stop_vm
        result = _stop_vm("sub-123", "rg-dev", "my-vm")
        assert "my-vm" in result
        assert "stopped" in result.lower() or "deallocated" in result.lower()

    @patch("tools.compute._client")
    def test_stop_vm_calls_deallocate(self, mock_client):
        poller = MagicMock()
        mock_client.return_value.virtual_machines.begin_deallocate.return_value = poller
        from tools.compute import _stop_vm
        _stop_vm("sub-123", "rg-dev", "my-vm")
        mock_client.return_value.virtual_machines.begin_deallocate.assert_called_once_with("rg-dev", "my-vm")
        poller.result.assert_called_once()

    @patch("tools.compute._client")
    def test_delete_vm_returns_confirmation(self, mock_client):
        mock_client.return_value.virtual_machines.begin_delete.return_value.result.return_value = None
        from tools.compute import _delete_vm
        result = _delete_vm("sub-123", "rg-dev", "my-vm")
        assert "my-vm" in result
        assert "deleted" in result.lower()

    @patch("tools.compute._client")
    def test_delete_vm_calls_begin_delete(self, mock_client):
        poller = MagicMock()
        mock_client.return_value.virtual_machines.begin_delete.return_value = poller
        from tools.compute import _delete_vm
        _delete_vm("sub-123", "rg-dev", "my-vm")
        mock_client.return_value.virtual_machines.begin_delete.assert_called_once_with("rg-dev", "my-vm")
        poller.result.assert_called_once()


# ---------------------------------------------------------------------------
# _list_vm_sizes
# ---------------------------------------------------------------------------

class TestListVMSizes:
    @patch("tools.compute._client")
    def test_formats_size_lines(self, mock_client):
        mock_client.return_value.virtual_machine_sizes.list.return_value = [
            _vm_size("Standard_D2s_v3", cores=2, memory_mb=8192),
            _vm_size("Standard_D4s_v3", cores=4, memory_mb=16384),
        ]
        from tools.compute import _list_vm_sizes
        result = _list_vm_sizes("sub-123", "eastus")
        assert "Standard_D2s_v3" in result
        assert "vCPUs=2" in result
        assert "Standard_D4s_v3" in result

    @patch("tools.compute._client")
    def test_truncates_to_40_sizes(self, mock_client):
        mock_client.return_value.virtual_machine_sizes.list.return_value = [
            _vm_size(f"Size_{i}") for i in range(60)
        ]
        from tools.compute import _list_vm_sizes
        result = _list_vm_sizes("sub-123", "eastus")
        # The footer mentions total count
        assert "60" in result
        # Only first 40 appear as list items
        assert result.count("- Size_") == 40

    @patch("tools.compute._client")
    def test_includes_region_in_footer(self, mock_client):
        mock_client.return_value.virtual_machine_sizes.list.return_value = [
            _vm_size("Standard_B1s"),
        ]
        from tools.compute import _list_vm_sizes
        result = _list_vm_sizes("sub-123", "eastus")
        assert "eastus" in result


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

class TestComputeToolRegistration:
    def test_stop_and_delete_are_destructive(self):
        from tools.compute import TOOLS
        tool_map = {t.name: t for t in TOOLS}
        assert tool_map["stop_virtual_machine"].destructive is True
        assert tool_map["delete_virtual_machine"].destructive is True

    def test_list_and_start_are_not_destructive(self):
        from tools.compute import TOOLS
        tool_map = {t.name: t for t in TOOLS}
        assert tool_map["list_virtual_machines"].destructive is False
        assert tool_map["start_virtual_machine"].destructive is False

    def test_expected_tools_registered(self):
        from tools.compute import TOOLS
        names = {t.name for t in TOOLS}
        expected = {
            "list_virtual_machines", "get_vm_status", "get_vm_details",
            "create_virtual_machine", "start_virtual_machine",
            "stop_virtual_machine", "delete_virtual_machine", "list_vm_sizes",
        }
        assert expected.issubset(names)
