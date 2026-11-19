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
    beat_schedule={
        "appointment-reminders": {"task": "app.tasks.send_appointment_reminders", "schedule": 900.0},
    },
)
