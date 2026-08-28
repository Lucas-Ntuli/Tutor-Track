output "resource_group_name" {
  value = azurerm_resource_group.tenant.name
}

output "key_vault_name" {
  value = azurerm_key_vault.tenant.name
}

output "key_vault_uri" {
  value = azurerm_key_vault.tenant.vault_uri
}

output "key_vault_id" {
  value = azurerm_key_vault.tenant.id
}

output "database_name" {
  value = azurerm_mssql_database.tenant.name
}

output "storage_account_name" {
  value = azurerm_storage_account.tenant.name
}