# Containers: api, worker (Celery + beat), web (nginx serving the SPA and proxying /api). Images are pushed to ECR by CI.

resource "aws_ecr_repository" "repo" {
  for_each             = toset(["api", "web"])
  name                 = "${local.name}-${each.key}"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.main.arn
  }
}

resource "aws_cloudwatch_log_group" "svc" {
  for_each          = toset(["api", "worker", "web"])
  name              = "/ecs/${local.name}/${each.key}"
  retention_in_days = 90
  kms_key_id        = aws_kms_key.main.arn
}

resource "aws_ecs_cluster" "main" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${local.name}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "execution_secrets" {
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = [aws_secretsmanager_secret.app.arn] },
      { Effect = "Allow", Action = ["kms:Decrypt"], Resource = [aws_kms_key.main.arn] },
    ]
  })
}

resource "aws_iam_role" "task" {
  name               = "${local.name}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy" "task_s3" {
  role = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], Resource = ["${aws_s3_bucket.documents.arn}/*"] },
      { Effect = "Allow", Action = ["s3:ListBucket"], Resource = [aws_s3_bucket.documents.arn] },
      { Effect = "Allow", Action = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"], Resource = [aws_kms_key.main.arn] },
    ]
  })
}

locals {
  app_env = [
    { name = "ENVIRONMENT", value = var.environment },
    { name = "STORAGE_BACKEND", value = "s3" },
    { name = "S3_BUCKET", value = aws_s3_bucket.documents.bucket },
    { name = "S3_REGION", value = var.region },
    { name = "COOKIE_SECURE", value = "true" },
    { name = "ENFORCE_MFA", value = "true" },
    { name = "CELERY_EAGER", value = "false" },
    { name = "CORS_ORIGINS", value = jsonencode(["https://${var.domain}"]) },
    { name = "FRONTEND_URL", value = "https://${var.domain}" },
    { name = "AI_PROVIDER", value = "simulated" },
    { name = "AI_PHI_ALLOWED", value = "false" },
  ]
  app_secrets = [for k in ["SECRET_KEY", "DATABASE_URL", "REDIS_URL"] : { name = k, valueFrom = "${aws_secretsmanager_secret.app.arn}:${k}::" }]
  log = { for s in ["api", "worker", "web"] : s => {
    logDriver = "awslogs"
    options = { "awslogs-group" = aws_cloudwatch_log_group.svc[s].name, "awslogs-region" = var.region, "awslogs-stream-prefix" = s }
  } }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  container_definitions = jsonencode([{
    name             = "api", image = "${aws_ecr_repository.repo["api"].repository_url}:${var.image_tag}", essential = true
    portMappings     = [{ containerPort = 8000 }]
    environment      = local.app_env, secrets = local.app_secrets, logConfiguration = local.log["api"]
    readonlyRootFilesystem = false
    healthCheck = { command = ["CMD-SHELL", "python -c \"import urllib.request;urllib.request.urlopen('http://localhost:8000/api/health')\""], interval = 15, retries = 5 }
  }])
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.name}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  container_definitions = jsonencode([{
    name    = "worker", image = "${aws_ecr_repository.repo["api"].repository_url}:${var.image_tag}", essential = true
    command = ["celery", "-A", "app.worker", "worker", "-B", "-s", "/tmp/celerybeat-schedule", "-l", "info", "--concurrency", "2"]
    environment = local.app_env, secrets = local.app_secrets, logConfiguration = local.log["worker"]
  }])
}

resource "aws_ecs_task_definition" "web" {
  family                   = "${local.name}-web"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn
  container_definitions = jsonencode([{
    name = "web", image = "${aws_ecr_repository.repo["web"].repository_url}:${var.image_tag}", essential = true
    portMappings = [{ containerPort = 80 }], logConfiguration = local.log["web"]
  }])
}

# ---------------------------------------------------------------- load balancer (TLS terminates here)
resource "aws_lb" "main" {
  name                       = local.name
  load_balancer_type         = "application"
  subnets                    = module.vpc.public_subnets
  security_groups            = [aws_security_group.alb.id]
  drop_invalid_header_fields = true
  enable_deletion_protection = var.environment == "production"
}

resource "aws_lb_target_group" "web" {
  name        = "${local.name}-web"
  port        = 80
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = module.vpc.vpc_id
  health_check { path = "/api/health" }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.acm_certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }
}

resource "aws_ecs_service" "svc" {
  for_each = {
    api    = { td = aws_ecs_task_definition.api.arn, count = 2, lb = false }
    worker = { td = aws_ecs_task_definition.worker.arn, count = 1, lb = false }
    web    = { td = aws_ecs_task_definition.web.arn, count = 2, lb = true }
  }
  name            = each.key
  cluster         = aws_ecs_cluster.main.id
  task_definition = each.value.td
  desired_count   = each.value.count
  launch_type     = "FARGATE"
  network_configuration {
    subnets         = module.vpc.private_subnets
    security_groups = [aws_security_group.app.id]
  }
  dynamic "load_balancer" {
    for_each = each.value.lb ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.web.arn
      container_name   = "web"
      container_port   = 80
    }
  }
  # The web (nginx) container proxies /api to the api service via ECS Service Connect / Cloud Map (configure
  # service_connect_configuration for your account) — see docs/DEPLOYMENT.md.
}
