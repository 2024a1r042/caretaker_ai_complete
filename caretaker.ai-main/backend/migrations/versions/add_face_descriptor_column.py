"""add face_descriptor column to caretakers

Revision ID: add_face_descriptor_column
Revises: 
Create Date: 2025-11-24 21:24:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_face_descriptor_column'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Add face_descriptor column as JSONB for PostgreSQL
    op.add_column('caretakers', 
                 sa.Column('face_descriptor', 
                          postgresql.JSONB(astext_type=sa.Text()), 
                          nullable=True))


def downgrade():
    op.drop_column('caretakers', 'face_descriptor')
