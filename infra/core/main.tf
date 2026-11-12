# Shared resources used by every phase. Names follow docs/contracts.md.

locals {
  name = var.project
}

# ---------------------------------------------------------------------------
# S3 data lake: raw/, clean/, quarantine/, models/, athena-results/
# ---------------------------------------------------------------------------
resource "aws_s3_bucket" "lake" {
  bucket = "${local.name}-lake-${var.suffix}"
}

resource "aws_s3_bucket_public_access_block" "lake" {
  bucket                  = aws_s3_bucket.lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "lake" {
  bucket = aws_s3_bucket.lake.id
  versioning_configuration {
    status = "Enabled" # keeps previous models/ if a bad one is promoted
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id

  rule {
    id     = "raw-to-glacier"
    status = "Enabled"
    filter {
      prefix = "raw/"
    }
    transition {
      days          = var.raw_to_glacier_days
      storage_class = "GLACIER"
    }
  }

  rule {
    id     = "expire-athena-results"
    status = "Enabled"
    filter {
      prefix = "athena-results/"
    }
    expiration {
      days = 7
    }
  }

  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

# Deny any request that is not over TLS (encryption in transit)
data "aws_iam_policy_document" "lake_tls_only" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]

    resources = [
      aws_s3_bucket.lake.arn,
      "${aws_s3_bucket.lake.arn}/*",
    ]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "lake" {
  bucket     = aws_s3_bucket.lake.id
  policy     = data.aws_iam_policy_document.lake_tls_only.json
  depends_on = [aws_s3_bucket_public_access_block.lake]
}

# Send "Object Created" events to EventBridge (used by phase B's rule)
resource "aws_s3_bucket_notification" "lake" {
  bucket      = aws_s3_bucket.lake.id
  eventbridge = true
}

# ---------------------------------------------------------------------------
# DynamoDB (on-demand)
# ---------------------------------------------------------------------------
resource "aws_dynamodb_table" "stations" {
  name         = "${local.name}-stations"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "station_id"

  attribute {
    name = "station_id"
    type = "S"
  }
  attribute {
    name = "geohash5"
    type = "S"
  }

  global_secondary_index {
    name            = "geohash5-index"
    hash_key        = "geohash5"
    projection_type = "ALL"
  }

  server_side_encryption {
    enabled = true
  }
}

resource "aws_dynamodb_table" "latest_prices" {
  name             = "${local.name}-latest-prices"
  billing_mode     = "PAY_PER_REQUEST"
  hash_key         = "station_id"
  range_key        = "fuel_type"
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES" # phase C compares old vs new price

  attribute {
    name = "station_id"
    type = "S"
  }
  attribute {
    name = "fuel_type"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }
}

resource "aws_dynamodb_table" "predictions" {
  name         = "${local.name}-predictions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "station_fuel" # "<station_id>#<fuel_type>"
  range_key    = "date"

  attribute {
    name = "station_fuel"
    type = "S"
  }
  attribute {
    name = "date"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  server_side_encryption {
    enabled = true
  }
}

resource "aws_dynamodb_table" "subscriptions" {
  name         = "${local.name}-subscriptions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "station_fuel" # "<station_id>#<fuel_type>"

  attribute {
    name = "user_id"
    type = "S"
  }
  attribute {
    name = "station_fuel"
    type = "S"
  }

  # phase C: "who follows this station?"
  global_secondary_index {
    name            = "station_fuel-index"
    hash_key        = "station_fuel"
    projection_type = "ALL"
  }

  server_side_encryption {
    enabled = true
  }
}

# ---------------------------------------------------------------------------
# Messaging: SNS topics + dead-letter queue
# ---------------------------------------------------------------------------
resource "aws_sns_topic" "admin_alerts" {
  name              = "${local.name}-admin-alerts"
  kms_master_key_id = "alias/aws/sns"
}

resource "aws_sns_topic_subscription" "admin_email" {
  for_each  = toset(var.admin_emails)
  topic_arn = aws_sns_topic.admin_alerts.arn
  protocol  = "email"
  endpoint  = each.value
}

resource "aws_sns_topic" "price_alerts" {
  name              = "${local.name}-price-alerts"
  kms_master_key_id = "alias/aws/sns"
}

resource "aws_sqs_queue" "dlq" {
  name                      = "${local.name}-dlq"
  message_retention_seconds = 1209600 # 14 days
  sqs_managed_sse_enabled   = true
}
