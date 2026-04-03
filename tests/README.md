# Tests

Unit tests for the azure-agent application. All Azure SDK calls and Anthropic API calls are mocked — no live Azure credentials or API keys are required to run the tests.

## Setup

Install test dependencies (in addition to the app's own `requirements.txt`):

```bash
pip install -r tests/requirements-test.txt
```

## Running

```bash
pytest tests/ -v
```

## Structure

| File | What's tested |
|---|---|
| `conftest.py` | Adds `app/` to `sys.path` so test files can import app modules |
| `test_agent.py` | `AzureAgent` top-level behaviour |
| `test_tools_base.py` | `Tool` base class and tool registry |
| `test_tools_resources.py` | Subscription and resource group tool functions |
| `test_tools_compute.py` | Virtual machine tool functions |
| `test_tools_storage.py` | Storage account and blob container tool functions |

## Coverage

### `test_agent.py`

Tests `AzureAgent` in `agent.py`:

- **Init** — starts with empty message history and no active groups
- **`_classify_groups`** — returns the correct groups for a given input; falls back to all groups on API error or invalid JSON response
- **`chat` (end_turn)** — returns assistant text; appends user and assistant messages to history; handles missing text block; handles unexpected stop reasons
- **`chat` (tool_use loop)** — executes the correct tool, appends a well-formed tool result message, then returns the final assistant text
- **`_execute_tool`** — delegates to the registered tool; returns an error string for unknown tools and for `TypeError` (bad arguments)
- **`_create_with_retry`** — returns immediately on success; retries on `RateLimitError`; raises after max retries are exhausted
- **`reset`** — clears message history and active group state
- **Default subscription injection** — prepends the subscription ID to the first user message when `AZURE_DEFAULT_SUBSCRIPTION_ID` is set

### `test_tools_base.py`

Tests `Tool` in `tools/base.py` and the registry in `tools/__init__.py`:

- **`Tool.definition`** — contains `name`, `description`, and `input_schema`; no extra keys
- **`Tool.destructive`** — defaults to `False`; can be set to `True`
- **`Tool.execute`** — passes kwargs through to the underlying function; returns the function's result; catches any `Exception` and returns a `[Azure error]` string including the exception type and message
- **`TOOL_REGISTRY`** — all tool names are unique; registry keys match tool names; core tools (`list_subscriptions`, `list_resource_groups`) are always present
- **`GROUP_DESCRIPTIONS`** — every key exists in `TOOL_GROUPS`
- **`definitions_for_groups`** — always includes core tools; includes tools from requested groups; silently ignores unknown group names; adds `cache_control: ephemeral` to the last definition only; does not duplicate core tools if `"core"` is passed explicitly; correctly combines multiple groups

### `test_tools_resources.py`

Tests the private functions in `tools/resources.py`:

- **`_list_subscriptions`** — formats one line per subscription including name, ID, and state; returns a "No subscriptions found" message when the list is empty
- **`_list_resource_groups`** — formats one line per resource group including name, location, and provisioning state; returns a "No resource groups found" message when empty; passes the subscription ID to the SDK client
- **`_create_resource_group`** — calls `create_or_update` with the correct resource group name and location dict; returns a confirmation string containing the RG name and provisioning state
- **`_delete_resource_group`** — calls `begin_delete` and waits on the poller; returns a confirmation string containing the RG name
- **`_list_resources`** — formats one line per resource including name, type, and location; returns a "No resources found" message when empty; filters by resource group name

### `test_tools_compute.py`

Tests the private functions in `tools/compute.py`:

- **`_list_vms`** — formats one line per VM including name, size, and location; returns "No VMs found" when empty
- **`_get_vm_status`** — returns the VM name and all non-empty status strings; filters out `None` and empty display statuses
- **`_start_vm`** — calls `begin_start` and waits on the poller; returns a confirmation string
- **`_stop_vm`** — calls `begin_deallocate` and waits on the poller; returns a confirmation string
- **`_delete_vm`** — calls `begin_delete` and waits on the poller; returns a confirmation string
- **`_list_vm_sizes`** — formats size lines with name, vCPU count, and memory; truncates output to the first 40 sizes; includes the total count and region name in the footer
- **Tool registration** — `stop_virtual_machine` and `delete_virtual_machine` are marked destructive; `list_virtual_machines` and `start_virtual_machine` are not; all expected tool names are present

### `test_tools_storage.py`

Tests the private functions in `tools/storage.py`:

- **`_list_storage_accounts`** — formats one line per account including name, kind, SKU, location, and access tier; returns "No storage accounts found" when empty
- **`_create_storage_account`** — waits on the poller; returns a confirmation string with account name, SKU, and location
- **`_delete_storage_account`** — calls `delete` with the correct resource group and account name; returns a confirmation string
- **`_list_blob_containers`** — formats one line per container including name and public access setting; returns "No blob containers found" when empty; filters by account name
- **Tool registration** — `delete_storage_account` is marked destructive; `list_storage_accounts` and `create_storage_account` are not; all expected tool names are present
