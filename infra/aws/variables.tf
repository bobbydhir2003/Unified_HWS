variable "region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "staging"
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production"
  }
}

variable "domain" {
  type        = string
  description = "Public hostname, e.g. app.example.org (DNS record created separately)"
}

variable "acm_certificate_arn" {
  type        = string
  description = "ACM certificate for var.domain"
}

variable "image_tag" {
  type        = string
  description = "Immutable image tag (git SHA) pushed by CI"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.medium"
}

output "alb_dns_name" { value = aws_lb.main.dns_name }
output "documents_bucket" { value = aws_s3_bucket.documents.bucket }
output "db_endpoint" { value = aws_db_instance.main.address }
