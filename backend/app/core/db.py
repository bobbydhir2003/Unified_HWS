from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.rls import APP_ROLE

engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

TENANT_KEY = "tenant_org_id"


def _apply_tenant(connection, org_id) -> None:
    connection.exec_driver_sql(f"SET LOCAL ROLE {APP_ROLE}")
    connection.exec_driver_sql("SELECT set_config('app.org_id', %s, true)", (str(org_id),))


@event.listens_for(Session, "after_begin")
def _tenant_on_begin(session: Session, transaction, connection) -> None:
    """Every transaction of a tenant-bound session runs as the restricted role with app.org_id set."""
    org_id = session.info.get(TENANT_KEY)
    if org_id and settings.rls_enabled:
        _apply_tenant(connection, org_id)


def bind_tenant(db: Session, org_id) -> None:
    """Bind a session to one organization for the rest of its life (applies to the open transaction too)."""
    if not settings.rls_enabled:
        return
    db.info[TENANT_KEY] = org_id
    if db.in_transaction():
        _apply_tenant(db.connection(), org_id)


def unbind_tenant(db: Session) -> None:
    """Platform-level operations that span organizations (e.g. creating an organization). Caller must hold org:manage."""
    db.info.pop(TENANT_KEY, None)
    if db.in_transaction():
        db.connection().exec_driver_sql("SET LOCAL ROLE NONE")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
