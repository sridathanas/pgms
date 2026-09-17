"""Create demo accounts for local testing.

Run from the project root:  python -m app.seed
Existing usernames are skipped, so it's safe to run more than once.
"""
from app import crud, models, schemas
from app.database import SessionLocal, engine

DEMO_USERS = [
    schemas.UserAccountCreate(
        username="admin", password="Admin@123", role=models.Role.ADMIN,
        name="Grid Administrator", email="admin@pgms.local", phone="9000000001",
    ),
    schemas.UserAccountCreate(
        username="operator", password="Operator@123", role=models.Role.OPERATOR,
        name="Control Room Operator", email="operator@pgms.local", phone="9000000002",
    ),
    schemas.UserAccountCreate(
        username="technician", password="Tech@123", role=models.Role.TECHNICIAN,
        name="Field Technician", email="technician@pgms.local", phone="9000000003",
        skillLevel="SENIOR", availabilityStatus="AVAILABLE", currentLocation="Kottayam",
    ),
]


def main():
    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for user in DEMO_USERS:
            if crud.get_user_by_username(db, user.username):
                print(f"skipped  {user.username} (already exists)")
                continue
            crud.create_user(db, user)
            print(f"created  {user.username:<11} role={user.role:<11} password={user.password}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
