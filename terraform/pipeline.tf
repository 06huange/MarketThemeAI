# Weekly pipeline: an ECS Fargate task started by EventBridge Scheduler.
#
# Networking: the task runs in the default VPC's public subnets with a public IP
# and no inbound rules. It only makes outbound calls (BigQuery, news sites, S3,
# ECR), so private subnets would only add a NAT Gateway (~$32/month) for nothing.

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

resource "aws_security_group" "pipeline" {
  name        = "${local.name}-pipeline"
  description = "Pipeline task: outbound only"
  vpc_id      = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_ecs_cluster" "this" {
  name = local.name
}

resource "aws_cloudwatch_log_group" "pipeline" {
  name              = "/ecs/${local.name}-pipeline"
  retention_in_days = 30
}

# Service-account key for BigQuery. Terraform creates the parameter with a
# placeholder; set the real value out of band so it never enters Terraform state:
#   aws ssm put-parameter --name <name> --type SecureString --overwrite --value file://key.json
resource "aws_ssm_parameter" "gcp_credentials" {
  name  = "/${local.name}/gcp-service-account-json"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}

# Execution role: what ECS itself needs to start the task (pull image, write logs, read the secret).
resource "aws_iam_role" "pipeline_execution" {
  name               = "${local.name}-pipeline-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy_attachment" "pipeline_execution" {
  role       = aws_iam_role.pipeline_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "pipeline_execution_secret" {
  role = aws_iam_role.pipeline_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ssm:GetParameters"]
      Resource = aws_ssm_parameter.gcp_credentials.arn
    }]
  })
}

# Task role: what the pipeline code can do. Only its own bucket prefixes.
resource "aws_iam_role" "pipeline_task" {
  name               = "${local.name}-pipeline-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy" "pipeline_task_s3" {
  role = aws_iam_role.pipeline_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Action    = ["s3:ListBucket"]
        Resource  = aws_s3_bucket.data.arn
        Condition = { StringLike = { "s3:prefix" = ["data/*", "dashboard/*"] } }
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = ["${aws_s3_bucket.data.arn}/data/*", "${aws_s3_bucket.data.arn}/dashboard/*"]
      },
    ]
  })
}

resource "aws_ecs_task_definition" "pipeline" {
  family                   = "${local.name}-pipeline"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.pipeline_cpu
  memory                   = var.pipeline_memory
  execution_role_arn       = aws_iam_role.pipeline_execution.arn
  task_role_arn            = aws_iam_role.pipeline_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = "pipeline"
    image     = "${aws_ecr_repository.this["pipeline"].repository_url}:${var.image_tag}"
    essential = true
    environment = [
      { name = "DATA_BUCKET", value = aws_s3_bucket.data.bucket },
    ]
    secrets = [
      { name = "GCP_SERVICE_ACCOUNT_JSON", valueFrom = aws_ssm_parameter.gcp_credentials.arn },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.pipeline.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "pipeline"
      }
    }
  }])

  # CI registers new revisions with new image tags; the schedule always runs the
  # latest revision, so Terraform must not roll the image back.
  lifecycle {
    ignore_changes = [container_definitions]
  }
}

# Scheduler role: allowed to start this task and hand it its two roles.
resource "aws_iam_role" "scheduler" {
  name = "${local.name}-scheduler"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "scheduler.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "scheduler" {
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Action    = ["ecs:RunTask"]
        Resource  = "arn:aws:ecs:${var.region}:${local.account_id}:task-definition/${aws_ecs_task_definition.pipeline.family}:*"
        Condition = { ArnLike = { "ecs:cluster" = aws_ecs_cluster.this.arn } }
      },
      {
        Effect   = "Allow"
        Action   = ["iam:PassRole"]
        Resource = [aws_iam_role.pipeline_execution.arn, aws_iam_role.pipeline_task.arn]
      },
    ]
  })
}

resource "aws_scheduler_schedule" "pipeline" {
  name                = "${local.name}-weekly-pipeline"
  schedule_expression = var.pipeline_schedule

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_ecs_cluster.this.arn
    role_arn = aws_iam_role.scheduler.arn

    ecs_parameters {
      # Family without a revision number = latest active revision, so CI deploys
      # are picked up without touching the schedule.
      task_definition_arn = "arn:aws:ecs:${var.region}:${local.account_id}:task-definition/${aws_ecs_task_definition.pipeline.family}"
      launch_type         = "FARGATE"
      task_count          = 1

      network_configuration {
        subnets          = data.aws_subnets.default.ids
        security_groups  = [aws_security_group.pipeline.id]
        assign_public_ip = true
      }
    }

    retry_policy {
      maximum_retry_attempts = 0
    }
  }
}
