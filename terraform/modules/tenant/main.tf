variable "tenant_name" {
  description = "URL-safe unique tenant identifier, e.g. 'brightpath-tutors'"
  type        = string
}

variable "location" {
  type    = string
  default = "westeurope"
}

variable "sql_server_id" {
  description = "ID of the shared SQL logical server that hosts each tenant's dedicated database"
  type        = string
}

variable "app_managed_identity_principal_id" {
  description = "Principal ID of the App's managed identity - granted access to this tenant's Key Vault"
  type        = string
}

variable "sku_tier" {
  description = "Allows differentiating tenant tiers (e.g. free vs paid) at provisioning time"
  type        = string
  default     = "Basic"
}

resource "azurerm_resource_group" "tenant" {
  name     = "tt-${var.tenant_name}-rg"
  location = var.location

  tags = {
    tenant     = var.tenant_name
    managed_by = "terraform"
    product    = "tutortrack"
  }
}

# --- Dedicated database per tenant. This is the isolation boundary:
# a bug in tenant A's queries, or a compromised tenant A credential,
# cannot touch tenant B's data - there is no shared table to leak across.
resource "azurerm_mssql_database" "tenant" {
  name        = "${var.tenant_name}-db"
  server_id   = var.sql_server_id
  sku_name    = var.sku_tier
  max_size_gb = 2

  tags = {
    tenant = var.tenant_name
  }
}

# --- Dedicated Key Vault per tenant. The app never sees a raw
# connection string in config - it fetches it at runtime from the
# vault scoped to that tenant, using its managed identity.
resource "azurerm_key_vault" "tenant" {
  name                       = "tt-${substr(var.tenant_name, 0, 10)}-kv"
  location                   = azurerm_resource_group.tenant.location
  resource_group_name        = azurerm_resource_group.tenant.name
  sku_name                   = "standard"
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  purge_protection_enabled   = true
  soft_delete_retention_days = 7

  tags = {
    tenant = var.tenant_name
  }
}

# --- Least-privilege access: the shared app identity can only read
# secrets, and only from THIS tenant's vault (granted per-module-call,
# not once globally). This is the RBAC boundary that AZ-500 covers.
resource "azurerm_role_assignment" "app_reads_tenant_secrets" {
  scope                = azurerm_key_vault.tenant.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = var.app_managed_identity_principal_id
}

resource "azurerm_key_vault_secret" "connection_string" {
  name         = "db-connection-string"
  key_vault_id = azurerm_key_vault.tenant.id
  value        = "Server=${var.sql_server_id};Database=${azurerm_mssql_database.tenant.name};Authentication=Active Directory Managed Identity;"

  depends_on = [azurerm_role_assignment.app_reads_tenant_secrets]
}

# --- Dedicated blob container per tenant, for uploaded files
# (worksheets, invoices) - same isolation principle as the database.
resource "azurerm_storage_account" "tenant" {
  name                     = "tt${replace(substr(var.tenant_name, 0, 15), "-", "")}sa"
  resource_group_name      = azurerm_resource_group.tenant.name
  location                 = azurerm_resource_group.tenant.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false

  tags = {
    tenant = var.tenant_name
  }
}

resource "azurerm_storage_container" "tenant_files" {
  name                  = "tenant-files"
  storage_account_name  = azurerm_storage_account.tenant.name
  container_access_type = "private"
}

data "azurerm_client_config" "current" {}