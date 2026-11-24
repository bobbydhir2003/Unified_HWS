"""Runtime protections: production configuration guard, per-IP rate limiting, lightweight metrics."""

import threading
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import Settings

INSECURE_SECRETS = {"dev-insecure-change-me-0123456789abcdef", "change-me", "dev-compose-secret-change-me-7f3a9c1e2b"}


def production_problems(s: Settings) -> list[str]:
    """Return reasons the configuration is unsafe for production (empty list = OK)."""
    if s.environment != "production":
        return []
    problems = []
    if s.secret_key in INSECURE_SECRETS or len(s.secret_key) < 32:
        problems.append("SECRET_KEY is a development default or shorter than 32 characters")
    if not s.credentials_encryption_key:
        problems.append("CREDENTIALS_ENCRYPTION_KEY must be set (encrypts stored AI provider keys)")
    if not s.cookie_secure:
        problems.append("COOKIE_SECURE must be true (HTTPS only)")
    if s.celery_eager:
        problems.append("CELERY_EAGER must be false in production")
    if s.storage_backend != "s3":
        problems.append("STORAGE_BACKEND must be s3 (encrypted object storage) in production")
    if any(o.startswith("http://") and "localhost" not in o for o in s.cors_origins):
        problems.append("CORS_ORIGINS must use https")
    if s.ai_phi_allowed and s.ai_provider == "simulated":
        problems.append("AI_PHI_ALLOWED set without an external provider — check configuration")
    if s.demo_mode:
        problems.append("DEMO_MODE must be off in production (it allows one-click sign-in to demo accounts)")
    if not s.enforce_mfa:
        problems.append("ENFORCE_MFA should be true for privileged roles in production")
    return problems


class RateLimiter:
    """Sliding-window limiter keyed by (client IP, bucket). Per-process: use an edge/WAF limiter in front of multiple replicas."""

    def __init__(self) -> None:
        self.hits: dict[tuple[str, str], deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: tuple[str, str], limit: int, window: float = 60.0) -> tuple[bool, int]:
        t = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and q[0] <= t - window:
                q.popleft()
            if len(q) >= limit:
                return False, int(window - (t - q[0])) + 1
            q.append(t)
            return True, 0


LIMITED_PREFIXES = {
    "/api/auth/login": "auth", "/api/auth/mfa/verify": "auth", "/api/auth/password/forgot": "auth", "/api/auth/password/reset": "auth",
    "/api/auth/invitations/accept": "auth", "/api/auth/demo-login": "auth", "/api/auth/demo/reset": "auth", "/api/integrations/": "webhook",
}


def rate_limit_bucket(path: str) -> str | None:
    if path.startswith("/api/v1/"):
        path = "/api/" + path[len("/api/v1/"):]
    for prefix, bucket in LIMITED_PREFIXES.items():
        if path.startswith(prefix):
            return bucket
    return None


def too_many(retry_after: int) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": "Too many requests. Please wait and try again."},
                        headers={"Retry-After": str(retry_after)})


class Metrics:
    """Prometheus text-format counters/histograms by method + route template (no ids, no PHI)."""

    BUCKETS = (0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5)

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.count: dict[tuple, int] = defaultdict(int)
        self.hist: dict[tuple, list] = defaultdict(lambda: [0] * (len(self.BUCKETS) + 1))
        self.total: dict[tuple, float] = defaultdict(float)

    def observe(self, method: str, route: str, status: int, seconds: float) -> None:
        with self.lock:
            self.count[(method, route, status // 100)] += 1
            h = self.hist[(method, route)]
            for i, b in enumerate(self.BUCKETS):
                if seconds <= b:
                    h[i] += 1
            h[-1] += 1
            self.total[(method, route)] += seconds

    def render(self) -> str:
        lines = ["# TYPE undeclared_http_requests_total counter"]
        with self.lock:
            for (m, r, s), n in sorted(self.count.items()):
                lines.append(f'undeclared_http_requests_total{{method="{m}",route="{r}",status="{s}xx"}} {n}')
            lines.append("# TYPE undeclared_http_request_duration_seconds histogram")
            for (m, r), h in sorted(self.hist.items()):
                for i, b in enumerate(self.BUCKETS):
                    lines.append(f'undeclared_http_request_duration_seconds_bucket{{method="{m}",route="{r}",le="{b}"}} {h[i]}')
                lines.append(f'undeclared_http_request_duration_seconds_bucket{{method="{m}",route="{r}",le="+Inf"}} {h[-1]}')
                lines.append(f'undeclared_http_request_duration_seconds_sum{{method="{m}",route="{r}"}} {self.total[(m, r)]:.4f}')
                lines.append(f'undeclared_http_request_duration_seconds_count{{method="{m}",route="{r}"}} {h[-1]}')
        return "\n".join(lines) + "\n"


def route_template(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", None) or "unmatched"
