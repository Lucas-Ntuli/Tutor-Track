variable "location" {
  type    = string
  default = "westeurope"
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "sql_admin_login" {
  type      = string
  sensitive = true
}

variable "sql_admin_password" {
  type      = string
  sensitive = true
}

variable "sql_aad_admin_login" {
  description = "AAD group or user that administers the SQL server (used instead of relying solely on SQL auth)"
  type        = string
}

variable "sql_aad_admin_object_id" {
  type = string
}

# --- The tenant registry. In a real signup flow, the provisioning
# pipeline (see .github/workflows/provision-tenant.yml) appends to
# this file programmatically and opens a PR / applies directly.
variable "tenants" {
  description = "List of active tenants - each entry provisions a full isolated environment"
  type = list(object({
    name = string
    tier = string
  }))
  default = []
}

# --- Observability -----------------------------------------------------

variable "alert_email_addresses" {
  description = "Emails notified by every alert rule (5xx spikes, latency, restarts, DTU pressure)"
  type        = list(string)
  default     = []
}

# --- Compute scaling -----------------------------------------------------

variable "min_replicas" {
  type    = number
  default = 1
}

variable "max_replicas" {
  type    = number
  default = 3
}