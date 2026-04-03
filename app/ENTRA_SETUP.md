# Entra ID Setup

The agent queries Microsoft Graph using your existing `az` CLI login (or service
principal). Graph requires separate permissions from ARM — follow the steps below.

---

## Option A — You log in with `az login` (most common)

Your personal user account needs one of these roles assigned in Entra ID:

| Role | What it grants |
|---|---|
| **Global Reader** | Read-only access to everything in Entra (recommended) |
| OR individually: | |
| Directory Readers | Basic directory read |
| + Security Reader | Security-related Entra data |

### Assign Global Reader via the portal

1. Go to **Microsoft Entra admin center** → **Roles & admins**
2. Click **Global Reader**
3. Click **+ Add assignments** → search for your username → **Add**

### Assign Global Reader via Azure CLI

```bash
# Find your object ID
az ad signed-in-user show --query id -o tsv

# Assign Global Reader (built-in role ID is fixed across all tenants)
az rest \
  --method POST \
  --uri "https://graph.microsoft.com/v1.0/roleManagement/directory/roleAssignments" \
  --body '{
    "principalId": "<your-object-id>",
    "roleDefinitionId": "f2ef992c-3afb-46b9-b7cf-a126ee74c451",
    "directoryScopeId": "/"
  }'
```

> **Note:** Only a Global Administrator or Privileged Role Administrator can
> assign directory roles. If you don't have that access, ask your Entra admin.

---

## Option B — You use a service principal (AZURE_CLIENT_ID / AZURE_CLIENT_SECRET)

The service principal needs **Microsoft Graph application permissions** granted
and admin-consented. These are NOT the same as Azure RBAC roles.

### Required Graph permissions (application, not delegated)

| Permission | Purpose |
|---|---|
| `User.Read.All` | Read all users |
| `Group.Read.All` | Read all groups and membership |
| `Application.Read.All` | Read app registrations and service principals |
| `Device.Read.All` | Read registered devices |
| `RoleManagement.Read.Directory` | Read directory role assignments |

### Grant permissions via the portal

1. **Azure portal** → **Microsoft Entra ID** → **App registrations**
2. Open your service principal's app registration
3. Click **API permissions** → **+ Add a permission** → **Microsoft Graph**
4. Choose **Application permissions**
5. Add each permission listed above
6. Click **Grant admin consent for \<your tenant\>** (requires Global Admin)

### Grant permissions via Azure CLI

```bash
# Get the service principal's object ID
SP_OBJECT_ID=$(az ad sp show --id $AZURE_CLIENT_ID --query id -o tsv)

# Get the Microsoft Graph service principal ID in your tenant
GRAPH_SP_ID=$(az ad sp show --id 00000003-0000-0000-c000-000000000000 --query id -o tsv)

# Permission GUIDs for Microsoft Graph (these are stable across all tenants)
declare -A PERMS=(
  ["User.Read.All"]="df021288-bdef-4463-88db-98f22de89214"
  ["Group.Read.All"]="5b567255-7703-4780-807c-7be8301ae99b"
  ["Application.Read.All"]="9a5d68dd-52b0-4cc2-bd40-abcf44ac3a30"
  ["Device.Read.All"]="7438b122-aefc-4978-80ed-43db9064d227"
  ["RoleManagement.Read.Directory"]="483bed4a-2ad3-4361-a73b-c83ccdbdc53c"
)

for PERM_NAME in "${!PERMS[@]}"; do
  PERM_ID="${PERMS[$PERM_NAME]}"
  echo "Granting $PERM_NAME ($PERM_ID)..."
  az rest \
    --method POST \
    --uri "https://graph.microsoft.com/v1.0/servicePrincipals/$GRAPH_SP_ID/appRoleAssignedTo" \
    --body "{
      \"principalId\": \"$SP_OBJECT_ID\",
      \"resourceId\": \"$GRAPH_SP_ID\",
      \"appRoleId\": \"$PERM_ID\"
    }"
done
```

> **Note:** This requires the calling identity to have the **Application Administrator**
> or **Global Administrator** role, and the `AppRoleAssignment.ReadWrite.All`
> application permission.

---

## Verify access

After assigning permissions, verify Graph access works:

```bash
# For az login users — get a Graph token and call /me
TOKEN=$(az account get-access-token --resource https://graph.microsoft.com --query accessToken -o tsv)
curl -H "Authorization: Bearer $TOKEN" https://graph.microsoft.com/v1.0/users?$top=1

# Should return a JSON object with a "value" array of users.
# A 403 means the role/permission is missing or not yet propagated (wait ~5 min).
```

---

## Sign-in activity (`signInActivity`)

The `get_entra_user` tool includes the user's last sign-in timestamp. This field
requires one of:

- **Global Reader** (already covered above), OR
- **Reports Reader** role

It is **not** available with Directory Readers alone. If you see `"lastSignInDateTime": null`
for all users, check that your account has Global Reader or Reports Reader.
