"""Add columns that were introduced after a database was first created.

SQLAlchemy's create_all() makes missing tables but never alters existing ones, so an older
pgms.db needs these one-off ALTER statements. Safe to run repeatedly.

    python -m app.migrate
"""
from sqlalchemy import inspect, text

from app import models
from app.database import engine

# table -> column -> SQL type used by ALTER TABLE
NEW_COLUMNS = {
    "user_accounts": {
        "approvalStatus": "VARCHAR NOT NULL DEFAULT 'APPROVED'",
        "createdAt": "DATETIME",
        "name": "VARCHAR",
        "email": "VARCHAR",
        "phone": "VARCHAR",
        "skillLevel": "VARCHAR",
        "availabilityStatus": "VARCHAR",
        "currentLocation": "VARCHAR",
        "consumerID": "INTEGER",
    },
    "alerts": {
        "description": "VARCHAR",
    },
    "maintenance_tickets": {
        "operatorID": "INTEGER",
        "assignedDate": "DATETIME",
        "resolvedDate": "DATETIME",
        "proofPhotoPath": "VARCHAR",
    },
}


def main():
    models.Base.metadata.create_all(bind=engine)  # new tables, e.g. system_settings
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    added = 0

    with engine.begin() as connection:
        for table, columns in NEW_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {c["name"] for c in inspector.get_columns(table)}
            for column, column_type in columns.items():
                if column in present:
                    continue
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"))
                print(f"added {table}.{column}")
                added += 1

    print(f"done: {added} column(s) added" if added else "done: database already up to date")


if __name__ == "__main__":
    main()
