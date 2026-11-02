import sqlite3
from sqlalchemy import create_engine, text

# SQLite database
SQLITE_PATH = "grand_cinema.db"

# PostgreSQL connection
POSTGRES_URL = (
    "postgresql+psycopg://postgres:admin123"
    "@localhost:5432/grande_cinema"
)

sqlite_conn = sqlite3.connect(SQLITE_PATH)
sqlite_conn.row_factory = sqlite3.Row

postgres_engine = create_engine(POSTGRES_URL)

# Tables in dependency order
TABLES = [
    "users",
    "films",
    "rooms",
    "screenings",
    "reservations",
    "reservation_seats",
    "tickets",
]

try:
    with postgres_engine.begin() as pg_conn:
        for table in TABLES:
            rows = sqlite_conn.execute(
                f'SELECT * FROM "{table}"'
            ).fetchall()

            if not rows:
                print(f"{table}: 0 rows in SQLite")
                continue

            columns = rows[0].keys()

            column_names = ", ".join(
                f'"{column}"' for column in columns
            )

            placeholders = ", ".join(
                f":{column}" for column in columns
            )

            query = text(
                f'INSERT INTO "{table}" '
                f"({column_names}) "
                f"OVERRIDING SYSTEM VALUE "
                f"VALUES ({placeholders}) "
                f"ON CONFLICT DO NOTHING"
            )

            for row in rows:
                data = dict(row)

                # Convert SQLite integer to PostgreSQL Boolean
                if table == "films" and "is_published" in data:
                    if data["is_published"] is not None:
                        data["is_published"] = bool(
                            data["is_published"]
                        )

                pg_conn.execute(query, data)

            print(f"{table}: {len(rows)} rows processed")

    print("Migration completed.")

finally:
    sqlite_conn.close()
    postgres_engine.dispose()