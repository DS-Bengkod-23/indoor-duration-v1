"""Initial migration - Create all tables

Revision ID: 001_initial
Revises: 
Create Date: 2026-02-06 10:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create rooms table
    op.create_table(
        'rooms',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
    )
    
    # Create persons table
    op.create_table(
        'persons',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False, index=True),
        sa.Column('nim_nip', sa.String(50), unique=True, nullable=False, index=True),
        sa.Column('photo_path', sa.String(500), nullable=True),
        sa.Column('embedding_id', sa.String(100), unique=True, nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    
    # Create cameras table
    op.create_table(
        'cameras',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, unique=True, index=True),
        sa.Column('rtsp_url', sa.String(500), nullable=False),
        sa.Column('room_id', UUID(as_uuid=True), sa.ForeignKey('rooms.id', ondelete='CASCADE'), nullable=False),
        sa.Column('camera_index', sa.Integer(), nullable=True),
        sa.Column('fps', sa.Integer(), default=30),
        sa.Column('resolution_width', sa.Integer(), default=640),
        sa.Column('resolution_height', sa.Integer(), default=480),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('is_online', sa.Boolean(), default=False),
        sa.Column('last_seen', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    
    # Create durations table
    op.create_table(
        'durations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('person_id', UUID(as_uuid=True), sa.ForeignKey('persons.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('track_id', sa.String(100), nullable=False, index=True),
        sa.Column('room_id', UUID(as_uuid=True), sa.ForeignKey('rooms.id', ondelete='CASCADE'), nullable=False),
        sa.Column('camera_id', UUID(as_uuid=True), sa.ForeignKey('cameras.id', ondelete='CASCADE'), nullable=False),
        sa.Column('check_in', sa.DateTime(), nullable=False, index=True),
        sa.Column('check_out', sa.DateTime(), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), default=0),
        sa.Column('confidence', sa.Float(), default=0.0),
        sa.Column('status', sa.String(20), default='UNKNOWN'),
        sa.Column('is_guest', sa.String(10), default='Y'),
        sa.Column('guest_label', sa.String(50), nullable=True),
        sa.Column('snapshot_path', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    
    # Create indexes
    op.create_index('idx_duration_track', 'durations', ['track_id', 'camera_id'])
    op.create_index('idx_duration_time', 'durations', ['check_in', 'check_out'])


def downgrade() -> None:
    op.drop_index('idx_duration_time', 'durations')
    op.drop_index('idx_duration_track', 'durations')
    op.drop_table('durations')
    op.drop_table('cameras')
    op.drop_table('persons')
    op.drop_table('rooms')
