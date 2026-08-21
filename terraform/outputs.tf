output "app_identity_client_id" {
  value = azurerm_user_assigned_identity.app.client_id
}

output "sql_server_fqdn" {
  value = azurerm_mssql_server.shared.fully_qualified_domain_name
}

output "tenant_key_vaults" {
  description = "Map of tenant name -> Key Vault URI, used by the app to resolve secrets per tenant"
  value       = { for k, v in module.tenant : k => v.key_vault_uri }
}

output "application_insights_connection_string" {
  value     = module.monitoring.application_insights_connection_string
  sensitive = true
}

output "container_app_fqdn" {
  value = azurerm_container_app.api.ingress[0].fqdn
}

output "container_registry_login_server" {
  value = azurerm_container_registry.shared.login_server
}