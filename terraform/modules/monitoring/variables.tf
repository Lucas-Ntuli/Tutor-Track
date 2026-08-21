variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "environment" {
  type = string
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "alert_email_addresses" {
  description = "Emails notified by every alert rule via the shared action group"
  type        = list(string)
  default     = []
}

variable "error_count_alert_threshold" {
  description = "Failed request count within the alert window that triggers the high-5xx alert"
  type        = number
  default     = 10
}

variable "latency_alert_threshold_ms" {
  type    = number
  default = 1500
}

variable "restart_count_alert_threshold" {
  description = "Kept here for reference by the root module's container-restart alert; not consumed directly inside this module (see main.tf note above container_app health)."
  type        = number
  default     = 3
}

variable "dtu_alert_threshold_percent" {
  type    = number
  default = 80
}

variable "sql_server_id" {
  description = "Resource ID of the shared SQL server to monitor DTU pressure for. Null skips that alert."
  type        = string
  default     = null
}

variable "tenant_key_vault_ids" {
  description = "Map of tenant name -> Key Vault resource ID, wired to diagnostic settings for audit logging"
  type        = map(string)
  default     = {}
}