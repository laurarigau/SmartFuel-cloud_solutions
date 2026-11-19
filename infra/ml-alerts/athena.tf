
resource "aws_glue_catalog_database" "ml" {
  name        = "smartfuel_ml"
  description = "SmartFuel clean fuel-price data for ML training"
}

resource "aws_glue_catalog_table" "clean_prices" {
  name          = "clean_prices"
  database_name = aws_glue_catalog_database.ml.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "EXTERNAL"                      = "TRUE"
    "classification"                = "parquet"
    "projection.enabled"            = "true"
    "projection.date.type"          = "date"
    "projection.date.range"         = "2026-11-01,NOW"
    "projection.date.format"        = "yyyy-MM-dd"
    "projection.date.interval"      = "1"
    "projection.date.interval.unit" = "DAYS"
    "storage.location.template"     = "s3://${var.retraining_lake_bucket}/clean/date=$${date}/"
  }

  storage_descriptor {
    location      = "s3://${var.retraining_lake_bucket}/clean/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "station_id"
      type = "string"
    }
    columns {
      name = "fuel_type"
      type = "string"
    }
    columns {
      name = "price_eur"
      type = "double"
    }
    columns {
      name = "ts"
      type = "timestamp"
    }
    columns {
      name = "station_name"
      type = "string"
    }
    columns {
      name = "municipality"
      type = "string"
    }
    columns {
      name = "province"
      type = "string"
    }
    columns {
      name = "lat"
      type = "double"
    }
    columns {
      name = "lon"
      type = "double"
    }
    columns {
      name = "geohash5"
      type = "string"
    }
  }

  partition_keys {
    name = "date"
    type = "string"
  }
}

resource "aws_athena_workgroup" "ml" {
  name        = "smartfuel-ml"
  description = "Athena queries for SmartFuel ML training"
  state       = "ENABLED"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = 1073741824

    result_configuration {
      output_location = "s3://${var.retraining_lake_bucket}/athena-results/ml/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}
