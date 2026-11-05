from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Float, DateTime, ForeignKey, Text, JSON
from config import DATABASE_URL

engine = create_engine(DATABASE_URL)
metadata = MetaData()

def upgrade():
    metadata.reflect(bind=engine)
    
    # Check if table already exists
    if 'medical_recommendations' not in metadata.tables:
        print("Creating table 'medical_recommendations'...")
        medical_recommendations = Table(
            'medical_recommendations', metadata,
            Column('id', Integer, primary_key=True, index=True),
            Column('care_recipient_id', Integer, ForeignKey('care_recipients.id', ondelete='CASCADE'), nullable=False),
            Column('metric', String, nullable=False),
            Column('severity', String, nullable=False),
            Column('message', Text, nullable=False),
            Column('trigger_value', Float, nullable=True),
            Column('reference_range', String, nullable=True),
            Column('source', String, default='rule'),
            Column('confidence_score', Float, default=1.0),
            Column('actions', JSON, default=list),
            Column('created_at', DateTime)
        )
        medical_recommendations.create(engine)
        print("Migration complete. Table created.")
    else:
        print("Table 'medical_recommendations' already exists.")

if __name__ == "__main__":
    print("Starting migration to add medical_recommendations table...")
    upgrade()
    print("Done.")
