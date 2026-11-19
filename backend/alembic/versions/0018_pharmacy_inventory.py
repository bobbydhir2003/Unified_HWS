"""pharmacy inventory

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-19 16:00:36.264404
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0018'
down_revision: str | None = '0017'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS purchase_request_seq START 5001")
    op.create_table('suppliers',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('contact_name', sa.String(length=120), nullable=True),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('phone', sa.String(length=40), nullable=True),
    sa.Column('lead_time_days', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_suppliers_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_suppliers')),
    sa.UniqueConstraint('organization_id', 'name', name=op.f('uq_suppliers_organization_id'))
    )
    op.create_index(op.f('ix_suppliers_organization_id'), 'suppliers', ['organization_id'], unique=False)
    op.create_table('inventory_items',
    sa.Column('kind', sa.String(length=12), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('sku', sa.String(length=40), nullable=False),
    sa.Column('ndc', sa.String(length=20), nullable=True),
    sa.Column('category', sa.String(length=60), nullable=True),
    sa.Column('form', sa.String(length=40), nullable=True),
    sa.Column('strength', sa.String(length=40), nullable=True),
    sa.Column('unit', sa.String(length=20), nullable=False),
    sa.Column('is_controlled', sa.Boolean(), nullable=False),
    sa.Column('reorder_point', sa.Integer(), nullable=False),
    sa.Column('reorder_qty', sa.Integer(), nullable=False),
    sa.Column('unit_cost_cents', sa.Integer(), nullable=False),
    sa.Column('preferred_supplier_id', sa.UUID(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.CheckConstraint("kind in ('medication','supply','equipment')", name=op.f('ck_inventory_items_kind')),
    sa.CheckConstraint('reorder_point >= 0 and reorder_qty >= 0', name=op.f('ck_inventory_items_reorder')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_inventory_items_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['preferred_supplier_id'], ['suppliers.id'], name=op.f('fk_inventory_items_preferred_supplier_id_suppliers'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_inventory_items')),
    sa.UniqueConstraint('organization_id', 'sku', name=op.f('uq_inventory_items_organization_id'))
    )
    op.create_index(op.f('ix_inventory_items_organization_id'), 'inventory_items', ['organization_id'], unique=False)
    op.create_table('inventory_lots',
    sa.Column('item_id', sa.UUID(), nullable=False),
    sa.Column('lot_number', sa.String(length=40), nullable=False),
    sa.Column('expiry_date', sa.Date(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['item_id'], ['inventory_items.id'], name=op.f('fk_inventory_lots_item_id_inventory_items'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_inventory_lots_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_inventory_lots')),
    sa.UniqueConstraint('item_id', 'lot_number', name=op.f('uq_inventory_lots_item_id'))
    )
    op.create_index(op.f('ix_inventory_lots_item_id'), 'inventory_lots', ['item_id'], unique=False)
    op.create_index(op.f('ix_inventory_lots_organization_id'), 'inventory_lots', ['organization_id'], unique=False)
    op.create_table('purchase_requests',
    sa.Column('number', sa.BigInteger(), server_default=sa.text("nextval('purchase_request_seq')"), nullable=False),
    sa.Column('facility_id', sa.UUID(), nullable=False),
    sa.Column('item_id', sa.UUID(), nullable=False),
    sa.Column('supplier_id', sa.UUID(), nullable=True),
    sa.Column('deliver_to_location_id', sa.UUID(), nullable=True),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('unit_cost_cents', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('source', sa.String(length=10), nullable=False),
    sa.Column('reason', sa.String(length=500), nullable=True),
    sa.Column('recommendation', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('case_id', sa.UUID(), nullable=True),
    sa.Column('requested_by_id', sa.UUID(), nullable=True),
    sa.Column('decided_by_id', sa.UUID(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decision_note', sa.String(length=500), nullable=True),
    sa.Column('ordered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('po_reference', sa.String(length=40), nullable=True),
    sa.Column('received_quantity', sa.Integer(), nullable=False),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.CheckConstraint("status in ('submitted','approved','rejected','ordered','received','cancelled')", name=op.f('ck_purchase_requests_status')),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_purchase_requests_quantity')),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_purchase_requests_case_id_cases'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['decided_by_id'], ['users.id'], name=op.f('fk_purchase_requests_decided_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deliver_to_location_id'], ['locations.id'], name=op.f('fk_purchase_requests_deliver_to_location_id_locations'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['facility_id'], ['clinics.id'], name=op.f('fk_purchase_requests_facility_id_clinics'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['item_id'], ['inventory_items.id'], name=op.f('fk_purchase_requests_item_id_inventory_items'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_purchase_requests_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['requested_by_id'], ['users.id'], name=op.f('fk_purchase_requests_requested_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], name=op.f('fk_purchase_requests_supplier_id_suppliers'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_purchase_requests'))
    )
    op.create_index('ix_pr_org_status', 'purchase_requests', ['organization_id', 'status'], unique=False)
    op.create_index(op.f('ix_purchase_requests_facility_id'), 'purchase_requests', ['facility_id'], unique=False)
    op.create_index(op.f('ix_purchase_requests_item_id'), 'purchase_requests', ['item_id'], unique=False)
    op.create_index(op.f('ix_purchase_requests_organization_id'), 'purchase_requests', ['organization_id'], unique=False)
    op.create_table('stock_balances',
    sa.Column('location_id', sa.UUID(), nullable=False),
    sa.Column('lot_id', sa.UUID(), nullable=False),
    sa.Column('item_id', sa.UUID(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.CheckConstraint('quantity >= 0', name=op.f('ck_stock_balances_non_negative')),
    sa.ForeignKeyConstraint(['item_id'], ['inventory_items.id'], name=op.f('fk_stock_balances_item_id_inventory_items'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['location_id'], ['locations.id'], name=op.f('fk_stock_balances_location_id_locations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['lot_id'], ['inventory_lots.id'], name=op.f('fk_stock_balances_lot_id_inventory_lots'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_stock_balances_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_stock_balances')),
    sa.UniqueConstraint('location_id', 'lot_id', name=op.f('uq_stock_balances_location_id'))
    )
    op.create_index(op.f('ix_stock_balances_item_id'), 'stock_balances', ['item_id'], unique=False)
    op.create_index(op.f('ix_stock_balances_location_id'), 'stock_balances', ['location_id'], unique=False)
    op.create_index(op.f('ix_stock_balances_lot_id'), 'stock_balances', ['lot_id'], unique=False)
    op.create_index(op.f('ix_stock_balances_organization_id'), 'stock_balances', ['organization_id'], unique=False)
    op.create_table('stock_movements',
    sa.Column('item_id', sa.UUID(), nullable=False),
    sa.Column('lot_id', sa.UUID(), nullable=False),
    sa.Column('location_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=15), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('balance_after', sa.Integer(), nullable=False),
    sa.Column('reason', sa.String(length=300), nullable=True),
    sa.Column('reference_type', sa.String(length=30), nullable=True),
    sa.Column('reference_id', sa.String(length=64), nullable=True),
    sa.Column('patient_id', sa.UUID(), nullable=True),
    sa.Column('actor_id', sa.UUID(), nullable=True),
    sa.Column('approved_by_id', sa.UUID(), nullable=True),
    sa.Column('at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.CheckConstraint("kind in ('receive','transfer_out','transfer_in','dispense','waste','adjust_up','adjust_down','return')", name=op.f('ck_stock_movements_kind')),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_stock_movements_positive')),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], name=op.f('fk_stock_movements_actor_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], name=op.f('fk_stock_movements_approved_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['item_id'], ['inventory_items.id'], name=op.f('fk_stock_movements_item_id_inventory_items'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['location_id'], ['locations.id'], name=op.f('fk_stock_movements_location_id_locations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['lot_id'], ['inventory_lots.id'], name=op.f('fk_stock_movements_lot_id_inventory_lots'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_stock_movements_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], name=op.f('fk_stock_movements_patient_id_patients'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_stock_movements'))
    )
    op.create_index('ix_movements_item_time', 'stock_movements', ['item_id', 'at'], unique=False)
    op.create_index(op.f('ix_stock_movements_item_id'), 'stock_movements', ['item_id'], unique=False)
    op.create_index(op.f('ix_stock_movements_location_id'), 'stock_movements', ['location_id'], unique=False)
    op.create_index(op.f('ix_stock_movements_lot_id'), 'stock_movements', ['lot_id'], unique=False)
    op.create_index(op.f('ix_stock_movements_organization_id'), 'stock_movements', ['organization_id'], unique=False)
    op.create_index(op.f('ix_stock_movements_patient_id'), 'stock_movements', ['patient_id'], unique=False)
    op.create_table('medication_verifications',
    sa.Column('order_id', sa.UUID(), nullable=False),
    sa.Column('patient_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('pharmacist_id', sa.UUID(), nullable=False),
    sa.Column('at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.CheckConstraint("status in ('verified','rejected','clarify')", name=op.f('ck_medication_verifications_status')),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_medication_verifications_order_id_orders'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_medication_verifications_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], name=op.f('fk_medication_verifications_patient_id_patients'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['pharmacist_id'], ['users.id'], name=op.f('fk_medication_verifications_pharmacist_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_medication_verifications')),
    sa.UniqueConstraint('order_id', name=op.f('uq_medication_verifications_order_id'))
    )
    op.create_index(op.f('ix_medication_verifications_order_id'), 'medication_verifications', ['order_id'], unique=False)
    op.create_index(op.f('ix_medication_verifications_organization_id'), 'medication_verifications', ['organization_id'], unique=False)
    op.create_index(op.f('ix_medication_verifications_patient_id'), 'medication_verifications', ['patient_id'], unique=False)
    op.execute("CREATE TRIGGER stock_movements_append_only BEFORE UPDATE OR DELETE ON stock_movements FOR EACH ROW EXECUTE FUNCTION forbid_mutation()")
    op.execute("CREATE TRIGGER med_verifications_append_only BEFORE UPDATE OR DELETE ON medication_verifications FOR EACH ROW EXECUTE FUNCTION forbid_mutation()")
    from app.core.rls import enable_rls_all

    enable_rls_all(op)


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_medication_verifications_patient_id'), table_name='medication_verifications')
    op.drop_index(op.f('ix_medication_verifications_organization_id'), table_name='medication_verifications')
    op.drop_index(op.f('ix_medication_verifications_order_id'), table_name='medication_verifications')
    op.drop_table('medication_verifications')
    op.drop_index(op.f('ix_stock_movements_patient_id'), table_name='stock_movements')
    op.drop_index(op.f('ix_stock_movements_organization_id'), table_name='stock_movements')
    op.drop_index(op.f('ix_stock_movements_lot_id'), table_name='stock_movements')
    op.drop_index(op.f('ix_stock_movements_location_id'), table_name='stock_movements')
    op.drop_index(op.f('ix_stock_movements_item_id'), table_name='stock_movements')
    op.drop_index('ix_movements_item_time', table_name='stock_movements')
    op.drop_table('stock_movements')
    op.drop_index(op.f('ix_stock_balances_organization_id'), table_name='stock_balances')
    op.drop_index(op.f('ix_stock_balances_lot_id'), table_name='stock_balances')
    op.drop_index(op.f('ix_stock_balances_location_id'), table_name='stock_balances')
    op.drop_index(op.f('ix_stock_balances_item_id'), table_name='stock_balances')
    op.drop_table('stock_balances')
    op.drop_index(op.f('ix_purchase_requests_organization_id'), table_name='purchase_requests')
    op.drop_index(op.f('ix_purchase_requests_item_id'), table_name='purchase_requests')
    op.drop_index(op.f('ix_purchase_requests_facility_id'), table_name='purchase_requests')
    op.drop_index('ix_pr_org_status', table_name='purchase_requests')
    op.drop_table('purchase_requests')
    op.drop_index(op.f('ix_inventory_lots_organization_id'), table_name='inventory_lots')
    op.drop_index(op.f('ix_inventory_lots_item_id'), table_name='inventory_lots')
    op.drop_table('inventory_lots')
    op.drop_index(op.f('ix_inventory_items_organization_id'), table_name='inventory_items')
    op.drop_table('inventory_items')
    op.drop_index(op.f('ix_suppliers_organization_id'), table_name='suppliers')
    op.drop_table('suppliers')
    op.execute("DROP SEQUENCE IF EXISTS purchase_request_seq")
    # ### end Alembic commands ###
