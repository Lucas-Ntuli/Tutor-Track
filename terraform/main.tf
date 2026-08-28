terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.90"
    }
  }
  # backend "azurerm" { ... }  # remote state, same reasoning as project 1
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
  }
}

data "azurerm_client_config" "current" {}

# --- Shared, product-level infrastructure (NOT per tenant) -----------

resource "azurerm_resource_group" "shared" {
  name     = "tutortrack-shared-rg"
  location = var.location
}

# One logical SQL server hosts every tenant's dedicated database.
# Isolation happens at the DATABASE level, not the server level -
# a reasonable middle ground between per-tenant servers (expensive,
# operationally heavy) and shared-schema (no real isolation).
resource "azurerm_mssql_server" "shared" {
  name                         = "tutortrack-sql-${var.environment}"
  resource_group_name          = azurerm_resource_group.shared.name
  location                     = azurerm_resource_group.shared.location
  version                      = "12.0"
  administrator_login          = var.sql_admin_login
  administrator_login_password = var.sql_admin_password

  azuread_administrator {
    login_username = var.sql_aad_admin_login
    object_id      = var.sql_aad_admin_object_id
  }
}

# The application's own identity - what every Container App instance
# runs as. It gets scoped, per-tenant, read-only Key Vault access via
# the tenant module (see role_assignment inside modules/tenant).
resource "azurerm_user_assigned_identity" "app" {
  name                = "tutortrack-app-identity"
  resource_group_name = azurerm_resource_group.shared.name
  location            = azurerm_resource_group.shared.location
}

# --- Per-tenant provisioning loop -------------------------------------
# Adding a customer = adding one entry to tenants.auto.tfvars.json and
# running `terraform apply`. This is what the provisioning pipeline
# automates on signup.

module "tenant" {
  source   = "./modules/tenant"
  for_each = { for t in var.tenants : t.name => t }

  tenant_name                       = each.value.name
  location                          = var.location
  sql_server_id                     = azurerm_mssql_server.shared.id
  app_managed_identity_principal_id = azurerm_user_assigned_identity.app.principal_id
  sku_tier                          = each.value.tier
}

# --- Observability --------------------------------------------------------
# One Log Analytics workspace + Application Insights instance for the
# whole product (see modules/monitoring for why this is shared rather
# than per-tenant, and what alerts it sets up).

module "monitoring" {
  source = "./modules/monitoring"

  resource_group_name = azurerm_resource_group.shared.name
  location            = var.location
  environment         = var.environment

  alert_email_addresses = var.alert_email_addresses
  sql_server_id         = azurerm_mssql_server.shared.id

  tenant_key_vault_ids = { for k, v in module.tenant : k => v.key_vault_id }
}

# --- Container registry ----------------------------------------------------
# Admin credentials stay disabled - the CI/CD identity pushes images via
# its own OIDC-federated RBAC role (AcrPush), and the app identity pulls
# via AcrPull below. Same least-privilege pattern as tenant Key Vault
# access: no shared static credential anywhere in the path.

resource "azurerm_container_registry" "shared" {
  name                = "${replace(var.environment, "-", "")}tutortrackacr"
  resource_group_name = azurerm_resource_group.shared.name
  location            = azurerm_resource_group.shared.location
  sku                 = "Basic"
  admin_enabled       = false
}

resource "azurerm_role_assignment" "app_pulls_images" {
  scope                = azurerm_container_registry.shared.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# --- Compute -----------------------------------------------------------
# Terraform owns the Container App's definition (identity, ingress,
# scaling, env vars) as the source of truth. deploy-app.yml then only
# updates the *image reference* on top of this baseline (`az containerapp
# update --image ...`) rather than redefining the whole app - avoids the
# classic "CI/CD and Terraform fight over who owns this resource" drift
# problem. The placeholder image below is only ever used on the very
# first `terraform apply`, before CI has pushed a real one.

resource "azurerm_container_app_environment" "shared" {
  name                       = "tutortrack-env-${var.environment}"
  resource_group_name        = azurerm_resource_group.shared.name
  location                   = azurerm_resource_group.shared.location
  log_analytics_workspace_id = module.monitoring.log_analytics_workspace_id
}

resource "azurerm_container_app" "api" {
  name                         = "tutortrack-api"
  resource_group_name          = azurerm_resource_group.shared.name
  container_app_environment_id = azurerm_container_app_environment.shared.id
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.shared.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  template {
    min_replicas = var.min_replicas
    max_replicas = var.max_replicas

    container {
      name   = "tutortrack-api"
      image  = "mcr.microsoft.com/k8se/quickstart:latest" # placeholder - CI overwrites on first deploy
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }
      env {
        name  = "APP_IDENTITY_CLIENT_ID"
        value = azurerm_user_assigned_identity.app.client_id
      }
      env {
        name        = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        secret_name = "appinsights-connection-string"
      }
      env {
        name  = "REQUIRE_API_KEY"
        value = var.environment == "prod" ? "true" : "false"
      }
      env {
        name  = "ENABLE_METRICS"
        value = "true"
      }
      env {
        name  = "ENABLE_TRACING"
        value = "true"
      }

      liveness_probe {
        transport = "HTTP"
        path      = "/health/live"
        port      = 8000
      }
      readiness_probe {
        transport = "HTTP"
        path      = "/health/ready"
        port      = 8000
      }
    }
  }

  secret {
    name  = "appinsights-connection-string"
    value = module.monitoring.application_insights_connection_string
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  # Prometheus scraping (Azure Monitor managed Prometheus) reads /metrics
  # directly over the app's own ingress in this starter kit rather than a
  # separate sidecar - simplest option for a single-service app; a bigger
  # deployment would move to Azure Monitor's native Container Apps
  # Prometheus scraping annotation once on a supported API version.

  lifecycle {
    ignore_changes = [
      # CI/CD updates the running image via `az containerapp update`,
      # not via Terraform - see deploy-app.yml. Terraform still owns
      # and can recreate everything else about this resource.
      template[0].container[0].image,
    ]
  }
}

# Lives here rather than inside the monitoring module: it needs to
# scope to the Container App, which itself needs Application
# Insights/Log Analytics to exist first (env vars, diagnostics) -
# putting this alert inside modules/monitoring would create a
# monitoring -> container app -> monitoring cycle.
resource "azurerm_monitor_metric_alert" "container_restarts" {
  name                = "tutortrack-container-restarts-${var.environment}"
  resource_group_name = azurerm_resource_group.shared.name
  scopes              = [azurerm_container_app.api.id]
  description         = "Container App replica(s) restarting repeatedly - likely crash-looping. Check /health/ready and startup logs first."
  severity            = 1
  frequency           = "PT5M"
  window_size         = "PT15M"

  criteria {
    metric_namespace = "Microsoft.App/containerApps"
    metric_name      = "RestartCount"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 3
  }

  action {
    action_group_id = module.monitoring.action_group_id
  }
}