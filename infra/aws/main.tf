# Undeclared — AWS reference deployment (ECS Fargate + RDS PostgreSQL + ElastiCache Redis + S3).
#
# STATUS: reference only. Not applied, and not validated locally (terraform was not installed in the build
# environment). Run `terraform init && terraform validate && terraform plan` and review with your security team.
# Applying this creates billable resources. Do not use with real PHI until a BAA with AWS is in place and the
# production readiness checklist (docs/PRODUCTION_READINESS.md) is complete.

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.60" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
  # backend "s3" { bucket = "<state-bucket>"  key = "undeclared/terraform.tfstate"  region = "us-east-1"  encrypt = true  dynamodb_table = "<lock-table>" }
}

provider "aws" {
  region = var.region
  default_tags { tags = { Project = "undeclared", Environment = var.environment, DataClass = "phi" } }
}

locals { name = "undeclared-${var.environment}" }

data "aws_availability_zones" "available" { state = "available" }

# ---------------------------------------------------------------- network
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.13"

  name                 = local.name
  cidr                 = "10.40.0.0/16"
  azs                  = slice(data.aws_availability_zones.available.names, 0, 2)
  public_subnets       = ["10.40.0.0/24", "10.40.1.0/24"]
  private_subnets      = ["10.40.10.0/24", "10.40.11.0/24"]
  database_subnets     = ["10.40.20.0/24", "10.40.21.0/24"]
  enable_nat_gateway   = true
  single_nat_gateway   = var.environment != "production"
  enable_dns_hostnames = true
  enable_flow_log                      = true
  create_flow_log_cloudwatch_log_group = true
  create_flow_log_cloudwatch_iam_role  = true
}

# ---------------------------------------------------------------- encryption key
resource "aws_kms_key" "main" {
  description         = "${local.name} data encryption"
  enable_key_rotation = true
}

# ---------------------------------------------------------------- secrets
resource "random_password" "db" {
  length  = 40
  special = false
}

resource "random_password" "app_secret" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret" "app" {
  name       = "${local.name}/app"
  kms_key_id = aws_kms_key.main.arn
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    SECRET_KEY   = random_password.app_secret.result
    DATABASE_URL = "postgresql+psycopg://undeclared:${random_password.db.result}@${aws_db_instance.main.address}:5432/undeclared?sslmode=require"
    REDIS_URL    = "rediss://${aws_elasticache_replication_group.main.primary_endpoint_address}:6379/0"
  })
}

# ---------------------------------------------------------------- security groups
resource "aws_security_group" "alb" {
  name   = "${local.name}-alb"
  vpc_id = module.vpc.vpc_id
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "app" {
  name   = "${local.name}-app"
  vpc_id = module.vpc.vpc_id
  ingress {
    from_port       = 80
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "data" {
  name   = "${local.name}-data"
  vpc_id = module.vpc.vpc_id
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }
  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }
}

# ---------------------------------------------------------------- PostgreSQL
resource "aws_db_parameter_group" "pg" {
  name   = "${local.name}-pg16"
  family = "postgres16"
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }
}

resource "aws_db_instance" "main" {
  identifier                      = local.name
  engine                          = "postgres"
  engine_version                  = "16"
  instance_class                  = var.db_instance_class
  allocated_storage               = 50
  max_allocated_storage           = 500
  storage_encrypted               = true
  kms_key_id                      = aws_kms_key.main.arn
  db_name                         = "undeclared"
  username                        = "undeclared"
  password                        = random_password.db.result
  db_subnet_group_name            = module.vpc.database_subnet_group_name
  vpc_security_group_ids          = [aws_security_group.data.id]
  parameter_group_name            = aws_db_parameter_group.pg.name
  multi_az                        = var.environment == "production"
  backup_retention_period         = 14 # point-in-time recovery window (days)
  backup_window                   = "06:00-07:00"
  deletion_protection             = true
  skip_final_snapshot             = false
  final_snapshot_identifier       = "${local.name}-final"
  copy_tags_to_snapshot           = true
  performance_insights_enabled    = true
  performance_insights_kms_key_id = aws_kms_key.main.arn
  enabled_cloudwatch_logs_exports = ["postgresql"]
  auto_minor_version_upgrade      = true
}

# ---------------------------------------------------------------- Redis
resource "aws_elasticache_subnet_group" "main" {
  name       = local.name
  subnet_ids = module.vpc.private_subnets
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id       = local.name
  description                = "Celery broker/result backend"
  engine                     = "redis"
  node_type                  = "cache.t4g.small"
  num_cache_clusters         = var.environment == "production" ? 2 : 1
  automatic_failover_enabled = var.environment == "production"
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  kms_key_id                 = aws_kms_key.main.arn
  subnet_group_name          = aws_elasticache_subnet_group.main.name
  security_group_ids         = [aws_security_group.data.id]
}

# ---------------------------------------------------------------- document storage
resource "aws_s3_bucket" "documents" {
  bucket = "${local.name}-documents-${data.aws_caller_identity.me.account_id}"
}

data "aws_caller_identity" "me" {}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket                  = aws_s3_bucket.documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.main.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_policy" "documents_tls_only" {
  bucket = aws_s3_bucket.documents.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.documents.arn, "${aws_s3_bucket.documents.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}

# ---------------------------------------------------------------- backups (in addition to RDS PITR)
resource "aws_backup_vault" "main" {
  name        = local.name
  kms_key_arn = aws_kms_key.main.arn
}

resource "aws_backup_plan" "main" {
  name = local.name
  rule {
    rule_name         = "daily"
    target_vault_name = aws_backup_vault.main.name
    schedule          = "cron(0 7 * * ? *)"
    lifecycle { delete_after = 35 }
  }
}

resource "aws_iam_role" "backup" {
  name = "${local.name}-backup"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "backup.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy_attachment" "backup" {
  role       = aws_iam_role.backup.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForBackup"
}

resource "aws_backup_selection" "main" {
  name         = local.name
  plan_id      = aws_backup_plan.main.id
  iam_role_arn = aws_iam_role.backup.arn
  resources    = [aws_db_instance.main.arn, aws_s3_bucket.documents.arn]
}
