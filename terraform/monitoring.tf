# Alerts go to one email via SNS. Confirm the subscription email AWS sends after apply.

resource "aws_sns_topic" "alerts" {
  name = "${local.name}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_sns_topic_policy" "alerts" {
  arn = aws_sns_topic.alerts.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sns:Publish"
      Principal = { Service = ["events.amazonaws.com", "cloudwatch.amazonaws.com"] }
      Resource  = aws_sns_topic.alerts.arn
    }]
  })
}

# Pipeline task stopped with a non-zero exit code (crash, OOM, failed step).
resource "aws_cloudwatch_event_rule" "pipeline_failed" {
  name = "${local.name}-pipeline-failed"
  event_pattern = jsonencode({
    source        = ["aws.ecs"]
    "detail-type" = ["ECS Task State Change"]
    detail = {
      clusterArn = [aws_ecs_cluster.this.arn]
      lastStatus = ["STOPPED"]
      containers = { exitCode = [{ "anything-but" = 0 }] }
    }
  })
}

resource "aws_cloudwatch_event_target" "pipeline_failed" {
  rule = aws_cloudwatch_event_rule.pipeline_failed.name
  arn  = aws_sns_topic.alerts.arn

  input_transformer {
    input_paths = {
      reason = "$.detail.stoppedReason"
      task   = "$.detail.taskArn"
    }
    input_template = "\"MarketThemeAI pipeline failed (<reason>). Task: <task>. Logs: CloudWatch group ${aws_cloudwatch_log_group.pipeline.name}\""
  }
}

resource "aws_cloudwatch_metric_alarm" "api_errors" {
  alarm_name          = "${local.name}-api-errors"
  alarm_description   = "The API returned errors (Lambda function errors) in the last 5 minutes."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.api.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

resource "aws_budgets_budget" "monthly" {
  name         = "${local.name}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }
}
