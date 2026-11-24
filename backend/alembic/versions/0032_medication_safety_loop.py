"""Closed-loop inpatient medication management: order lifecycle statuses, verification history, eMAR.

* orders: new statuses (pending_verification, clarification_needed, rejected, active, on_hold, discontinued), new order
  types (procedure, nursing), discontinue attribution.
* medication_verifications: one order may have several pharmacist decisions (clarify → verify); manual interaction
  review flag.
* medication_administrations (+ witnesses): append-only eMAR; one documented event per scheduled dose.
* Data: medication orders for currently admitted patients that were signed but never decided move to
  pending_verification; decided ones take the matching state. Outpatient prescriptions are unchanged.

Revision ID: 0032
Revises: 0031
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import enable_rls_all

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_STATUSES = ("draft", "signed", "transmitted", "in_progress", "resulted", "completed", "cancelled")
NEW_STATUSES = OLD_STATUSES + ("pending_verification", "clarification_needed", "rejected", "active", "on_hold", "discontinued")
OLD_TYPES = ("medication", "lab", "imaging", "referral")
NEW_TYPES = OLD_TYPES + ("procedure", "nursing")


def _in(values) -> str:
    return "(" + ",".join(f"'{v}'" for v in values) + ")"


def _checks(statuses, types) -> None:
    op.execute("ALTER TABLE orders DROP CONSTRAINT ck_orders_status")
    op.execute(f"ALTER TABLE orders ADD CONSTRAINT ck_orders_status CHECK (status in {_in(statuses)})")
    op.execute("ALTER TABLE orders DROP CONSTRAINT ck_orders_type")
    op.execute(f"ALTER TABLE orders ADD CONSTRAINT ck_orders_type CHECK (order_type in {_in(types)})")


def upgrade() -> None:
    _checks(NEW_STATUSES, NEW_TYPES)
    op.add_column("orders", sa.Column("discontinued_at", sa.DateTime(timezone=True)))
    op.add_column("orders", sa.Column("discontinued_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", name="fk_orders_discontinued_by_id_users")))

    op.execute("ALTER TABLE medication_verifications DROP CONSTRAINT uq_medication_verifications_order_id")
    op.add_column("medication_verifications", sa.Column("manual_interaction_review", sa.Boolean(), nullable=False, server_default="false"))

    op.create_table(
        "medication_administrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("stay_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("inpatient_stays.id", ondelete="SET NULL"), index=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("dose", sa.String(60)),
        sa.Column("route", sa.String(40)),
        sa.Column("site", sa.String(60)),
        sa.Column("reason", sa.Text()),
        sa.Column("late", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("administered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("administered_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("dispense_movement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stock_movements.id", ondelete="SET NULL")),
        sa.Column("scan", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("requires_witness", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("order_id", "scheduled_for", name="uq_med_admin_order_slot"),
        sa.CheckConstraint("status in ('given','held','refused','omitted')", name="ck_medication_administrations_status"),
        sa.CheckConstraint("status = 'given' OR reason IS NOT NULL", name="ck_medication_administrations_reason_required"),
    )
    op.create_index("ix_med_admin_patient_time", "medication_administrations", ["patient_id", "administered_at"])
    op.create_table(
        "medication_administration_witnesses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("administration_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("medication_administrations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("witness_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("note", sa.String(300)),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("administration_id", name="uq_medication_administration_witnesses_administration_id"),
    )
    for t in ("medication_administrations", "medication_administration_witnesses"):
        op.execute(f"CREATE TRIGGER {t}_append_only BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION forbid_mutation()")

    # In-flight inpatient medication orders adopt the lifecycle (latest pharmacist decision wins).
    op.execute("""
UPDATE orders o SET
  status = COALESCE((SELECT CASE v.status WHEN 'verified' THEN 'active' WHEN 'rejected' THEN 'rejected'
                                          ELSE 'clarification_needed' END
                     FROM medication_verifications v WHERE v.order_id = o.id ORDER BY v.at DESC LIMIT 1),
                    'pending_verification'),
  details = o.details || '{"setting": "inpatient"}'::jsonb
WHERE o.order_type = 'medication' AND o.status IN ('signed','transmitted','completed')
  AND EXISTS (SELECT 1 FROM inpatient_stays s WHERE s.patient_id = o.patient_id
              AND s.status IN ('admitted','discharge_ordered') AND o.signed_at >= s.admitted_at)
""")
    _normalize_legacy_details()
    enable_rls_all(op)


ROUTES = {"iv": "intravenous", "sc": "subcutaneous", "subcut": "subcutaneous", "po": "oral", "im": "intramuscular"}
FREQ = {"q24h": "daily", "daily": "daily", "bid": "bid", "tid": "tid", "qid": "qid", "q4h": "q4h", "q6h": "q6h", "q8h": "q8h", "q12h": "q12h"}


def _normalize_legacy_details() -> None:
    """Older synthetic inpatient orders stored {drug, dose, route: IV, frequency: 'q8h PRN'}; map them to the structured
    fields the eMAR uses. Values that can't be mapped are left for the prescriber (the order then has no schedule)."""
    import json

    conn = op.get_bind()
    rows = conn.exec_driver_sql("SELECT id, details FROM orders WHERE order_type = 'medication' AND details ? 'drug' AND NOT details ? 'name'").all()
    for oid, d in rows:
        d = dict(d or {})
        freq = str(d.get("frequency") or "").lower()
        prn = "prn" in freq
        base = freq.replace("prn", "").strip()
        d["name"] = d.get("drug")
        d.setdefault("strength", d.get("dose"))
        d["route"] = ROUTES.get(str(d.get("route") or "").lower(), d.get("route"))
        d["frequency"] = "prn" if prn else FREQ.get(base)
        if prn and base.startswith("q") and base.endswith("h") and base[1:-1].isdigit():
            d["prn_interval_hours"] = int(base[1:-1])
        d.setdefault("sig", freq or "as ordered")
        conn.exec_driver_sql("UPDATE orders SET details = %s::jsonb WHERE id = %s", (json.dumps(d), oid))


def downgrade() -> None:
    op.execute("""UPDATE orders SET status = CASE
        WHEN status IN ('pending_verification','clarification_needed','active','on_hold') THEN 'signed'
        WHEN status IN ('rejected','discontinued') THEN 'cancelled' ELSE status END""")
    op.execute("UPDATE orders SET order_type = 'referral', status = 'cancelled' WHERE order_type IN ('procedure','nursing')")
    op.drop_table("medication_administration_witnesses")
    op.drop_table("medication_administrations")
    # Restoring the old one-decision-per-order shape drops superseded decisions (downgrade only; trigger re-enabled).
    op.execute("ALTER TABLE medication_verifications DISABLE TRIGGER med_verifications_append_only")
    op.execute("""DELETE FROM medication_verifications a USING medication_verifications b
                  WHERE a.order_id = b.order_id AND (a.at, a.id) < (b.at, b.id)""")
    op.execute("ALTER TABLE medication_verifications ENABLE TRIGGER med_verifications_append_only")
    op.drop_column("medication_verifications", "manual_interaction_review")
    op.execute("ALTER TABLE medication_verifications ADD CONSTRAINT uq_medication_verifications_order_id UNIQUE (order_id)")
    op.drop_column("orders", "discontinued_by_id")
    op.drop_column("orders", "discontinued_at")
    _checks(OLD_STATUSES, OLD_TYPES)
