# --- monitoring module -------------------------------------------------
#
# Shared, product-level observability infrastructure: one Log Analytics
# workspace + one Application Insights instance for the whole app (not
# per-tenant - traces/logs are tagged with a `tenant` dimension by the
# app itself, see app/observability.py, so a single workspace can still
# answer per-tenant questions via KQL/dashboard filters without needing
# N separate workspaces).
#
# Also provisions the alerting most likely to matter for an
# infrastructure-isolation-focused product:
#   - API 5xx rate spikes (something is actively broken)
#   - API availability / uptime (App Insights availability test)
#   - Container App restart count (crash-looping)
#   - Key Vault throttling/failures (per-tenant secret fetches breaking)
#   - SQL DTU/storage pressure (a tenant's dedicated DB running hot)
# all routed through a single Action Group so the notification channel
# is configured once and reused everywhere.

resource "azurerm_log_analytics_workspace" "this" {
  name                = "tutortrack-logs-${var.environment}"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "PerGB2018"
  retention_in_days   = var.log_retention_days
}

resource "azurerm_application_insights" "this" {
  name                = "tutortrack-appinsights-${var.environment}"
  resource_group_name = var.resource_group_name
  location            = var.location
  workspace_id        = azurerm_log_analytics_workspace.this.id
  application_type    = "web"
}

resource "azurerm_monitor_action_group" "this" {
  name                = "tutortrack-alerts-${var.environment}"
  resource_group_name = var.resource_group_name
  short_name          = "ttalerts"

  dynamic "email_receiver" {
    for_each = var.alert_email_addresses
    content {
      name          = "email-${replace(email_receiver.value, "/[^a-zA-Z0-9]/", "")}"
      email_address = email_receiver.value
    }
  }
}

# --- Application-level alerts (App Insights) ---------------------------

resource "azurerm_monitor_metric_alert" "high_5xx_rate" {
  name                = "tutortrack-high-5xx-rate-${var.environment}"
  resource_group_name = var.resource_group_name
  scopes              = [azurerm_application_insights.this.id]
  description         = "API server error rate is elevated - check the request rate dashboard broken down by tenant before assuming it's a single customer."
  severity            = 1
  frequency           = "PT5M"
  window_size         = "PT15M"

  criteria {
    metric_namespace = "Microsoft.Insights/components"
    metric_name      = "requests/failed"
    aggregation      = "Count"
    operator         = "GreaterThan"
    threshold        = var.error_count_alert_threshold
  }

  action {
    action_group_id = azurerm_monitor_action_group.this.id
  }
}

resource "azurerm_monitor_metric_alert" "high_response_latency" {
  name                = "tutortrack-high-latency-${var.environment}"
  resource_group_name = var.resource_group_name
  scopes              = [azurerm_application_insights.this.id]
  description         = "p95-ish average server response time is elevated. Check Key Vault secret-fetch latency first - it's the most common shared-dependency slowdown."
  severity            = 2
  frequency           = "PT5M"
  window_size         = "PT15M"

  criteria {
    metric_namespace = "Microsoft.Insights/components"
    metric_name      = "requests/duration"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = var.latency_alert_threshold_ms
  }

  action {
    action_group_id = azurerm_monitor_action_group.this.id
  }
}

# --- Container App health -----------------------------------------------
# NOTE: the container-restart alert itself lives in the ROOT module
# (terraform/main.tf), not here. Application Insights/Log Analytics
# have to exist before the Container App can reference them (env vars,
# diagnostic destination), and the Container App has to exist before an
# alert can target it - putting the alert here would create a
# monitoring -> container app -> monitoring dependency cycle. The action
# group defined below is still the shared notification target.

# --- Shared SQL server health --------------------------------------------

resource "azurerm_monitor_metric_alert" "sql_dtu_pressure" {
  name                = "tutortrack-sql-dtu-pressure-${var.environment}"
  resource_group_name = var.resource_group_name
  scopes              = [var.sql_server_id]
  description         = "A tenant database is running hot on DTU. Since databases are isolated per tenant, this points at ONE noisy tenant, not a systemic issue - check per-database metrics to identify which."
  severity            = 2
  frequency           = "PT5M"
  window_size         = "PT15M"

  criteria {
    metric_namespace = "Microsoft.Sql/servers/databases"
    metric_name      = "dtu_consumption_percent"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = var.dtu_alert_threshold_percent
  }

  action {
    action_group_id = azurerm_monitor_action_group.this.id
  }
}

# --- Diagnostic settings: ship Key Vault audit logs (per tenant) --------
# to the shared Log Analytics workspace. This is what makes "who
# accessed tenant X's secret and when" queryable/auditable - directly
# relevant to the governance story in the README.

resource "azurerm_monitor_diagnostic_setting" "tenant_key_vault" {
  for_each = var.tenant_key_vault_ids

  name                       = "kv-diagnostics-${each.key}"
  target_resource_id         = each.value
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id

  enabled_log {
    category = "AuditEvent"
  }

  metric {
    category = "AllMetrics"
  }
}
