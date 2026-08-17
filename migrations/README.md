# Database migrations

Run `alembic upgrade head` to create or update a versioned application schema.
The URL is resolved from `STUDY_COMPANION_DATABASE_URL`, then `DATABASE_URL`,
then the local SQLite default in `alembic.ini`.

For an existing database previously created by SQLAlchemy `create_all`, make a
backup and run `python -m modules.persistence.schema_migration` first.  The
command refuses to stamp the baseline unless all application-owned tables
match the current ORM metadata.
