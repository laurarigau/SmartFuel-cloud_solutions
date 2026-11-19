resource "aws_ecr_repository" "ml_predict" {
  name                 = "${var.project}-predict-ml"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}