"""Initial schema."""
from alembic import op
import sqlalchemy as sa
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('users', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('email', sa.String(255), nullable=False), sa.Column('password_hash', sa.String(255), nullable=False), sa.Column('role', sa.String(20), nullable=False))
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_table('records', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('title', sa.String(255), nullable=False), sa.Column('value', sa.Float(), nullable=False), sa.Column('category', sa.String(100), nullable=False), sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False), sa.Column('creator_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True))
    op.create_index('ix_records_category', 'records', ['category'])
    op.create_index('ix_records_timestamp', 'records', ['timestamp'])
    op.create_table('audit_logs', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True), sa.Column('action', sa.String(100), nullable=False), sa.Column('detail', sa.Text(), nullable=False), sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False))

def downgrade():
    op.drop_table('audit_logs')
    op.drop_table('records')
    op.drop_table('users')
