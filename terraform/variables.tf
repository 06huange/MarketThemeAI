variable "project" {
  type    = string
  default = "marketthemeai"
}

variable "environment" {
  description = "Deployment environment, e.g. dev or prod."
  type        = string
}

variable "region" {
  type    = string
  default = "us-west-2"
}

variable "github_repository" {
  description = "owner/repo allowed to deploy through GitHub Actions OIDC."
  type        = string
  default     = "06huange/MarketThemeAI"
}

variable "image_tag" {
  description = "Image tag for the initial deploy. Later deploys come from CI, which Terraform ignores."
  type        = string
}

variable "alert_email" {
  description = "Receives pipeline-failure, API-error, and budget alerts. Pass via TF_VAR_alert_email so it stays out of the repo."
  type        = string
}

variable "cors_origins" {
  description = "Origins allowed to call the API from a browser."
  type        = list(string)
  default     = ["*"]
}

variable "pipeline_schedule" {
  description = "When the weekly pipeline runs (EventBridge Scheduler expression)."
  type        = string
  default     = "cron(0 16 ? * MON *)" # Mondays 16:00 UTC
}

variable "pipeline_cpu" {
  type    = number
  default = 2048
}

variable "pipeline_memory" {
  type    = number
  default = 8192
}

variable "monthly_budget_usd" {
  type    = number
  default = 5
}
