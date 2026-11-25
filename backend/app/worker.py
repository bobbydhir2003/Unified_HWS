"""Celery application. Run: `celery -A app.worker worker -B -l info`."""

from celery import Celery

from app.core.config import settings

celery_app = Celery("undeclared", broker=settings.redis_url, backend=settings.redis_url, include=["app.tasks"])
celery_app.conf.update(
    task_always_eager=settings.celery_eager,
    task_eager_propagates=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    timezone="UTC",
    task_default_queue="default",
    # Slow AI work must never starve time-critical engine jobs: run workers with -Q default,engine,ai.
    task_routes={"app.tasks.dispatch_events": {"queue": "engine"}, "app.tasks.run_monitors": {"queue": "engine"},
                 "app.tasks.escalate_cases": {"queue": "engine"}, "app.tasks.process_document": {"queue": "ai"},
                 "app.tasks.case_assist": {"queue": "ai"}},
    beat_schedule={
        "appointment-reminders": {"task": "app.tasks.send_appointment_reminders", "schedule": 900.0},
        "engine-dispatch": {"task": "app.tasks.dispatch_events", "schedule": 10.0},
        "engine-escalations": {"task": "app.tasks.escalate_cases", "schedule": 60.0},
        "engine-monitors": {"task": "app.tasks.run_monitors", "schedule": 300.0},
        "assist-retention": {"task": "app.tasks.assist_retention", "schedule": 3600.0},
    },
)
