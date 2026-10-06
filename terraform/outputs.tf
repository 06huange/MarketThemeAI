output "api_url" {
  description = "Public API base URL; set as NEXT_PUBLIC_API_URL in Vercel."
  value       = aws_lambda_function_url.api.function_url
}

output "data_bucket" {
  value = aws_s3_bucket.data.bucket
}

output "ecr_repositories" {
  value = { for k, repo in aws_ecr_repository.this : k => repo.repository_url }
}

output "github_deploy_role_arn" {
  description = "Set as the AWS_DEPLOY_ROLE_ARN variable in the GitHub repo."
  value       = aws_iam_role.github_deploy.arn
}

output "ecs_cluster" {
  value = aws_ecs_cluster.this.name
}

output "pipeline_task_family" {
  value = aws_ecs_task_definition.pipeline.family
}

output "pipeline_network" {
  description = "For running the pipeline on demand with `aws ecs run-task`."
  value = {
    subnets         = data.aws_subnets.default.ids
    security_groups = [aws_security_group.pipeline.id]
  }
}

output "gcp_credentials_parameter" {
  value = aws_ssm_parameter.gcp_credentials.name
}
