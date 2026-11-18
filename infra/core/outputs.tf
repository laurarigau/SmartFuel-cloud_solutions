# Read by the other stacks through terraform_remote_state

output "lake_bucket" {
  value = aws_s3_bucket.lake.id
}

output "lake_bucket_arn" {
  value = aws_s3_bucket.lake.arn
}

output "tables" {
  value = {
    stations      = aws_dynamodb_table.stations.name
    latest_prices = aws_dynamodb_table.latest_prices.name
    predictions   = aws_dynamodb_table.predictions.name
    subscriptions = aws_dynamodb_table.subscriptions.name
  }
}

output "table_arns" {
  value = {
    stations      = aws_dynamodb_table.stations.arn
    latest_prices = aws_dynamodb_table.latest_prices.arn
    predictions   = aws_dynamodb_table.predictions.arn
    subscriptions = aws_dynamodb_table.subscriptions.arn
  }
}

output "latest_prices_stream_arn" {
  value = aws_dynamodb_table.latest_prices.stream_arn
}


output "admin_alerts_topic_arn" {
  value = try(aws_sns_topic.admin_alerts[0].arn, null)
}

output "price_alerts_topic_arn" {
  value = try(aws_sns_topic.price_alerts[0].arn, null)
}

output "dlq_arn" {
  value = try(aws_sqs_queue.dlq[0].arn, null)
}

output "dlq_url" {
  value = try(aws_sqs_queue.dlq[0].url, null)
}