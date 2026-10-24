import argparse

from sqlalchemy import create_engine, text

from softwiki.source_store.db import Base
from softwiki.source_store import models

TABLES = ["documents", "chunks", "claims", "entities", "relationships", "events"]
SERIAL_TABLES = ["documents", "chunks", "entities", "relationships", "events"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="SQLite file path or URL")
    parser.add_argument("--target", required=True, help="PostgreSQL URL")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()

    source_url = args.source if "://" in args.source else f"sqlite:///{args.source}"
    source = create_engine(source_url)
    target = create_engine(args.target)
    tables = [Base.metadata.tables[name] for name in TABLES]
    Base.metadata.create_all(target, tables=tables)

    with source.connect() as src, target.begin() as dst:
        if args.replace:
            for name in reversed(TABLES):
                dst.execute(text(f'TRUNCATE TABLE "{name}" RESTART IDENTITY CASCADE'))

        for name, table in zip(TABLES, tables):
            rows = [
                dict(row._mapping)
                for row in src.execute(text(f'SELECT * FROM "{name}"'))
            ]
            for start in range(0, len(rows), args.batch_size):
                dst.execute(table.insert(), rows[start:start + args.batch_size])
            print(f"{name}: {len(rows)}")

        if target.dialect.name == "postgresql":
            for name in SERIAL_TABLES:
                dst.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{name}','id'), "
                    f"COALESCE((SELECT MAX(id) FROM \"{name}\"), 1), true)"
                ))

    print("migration complete")


if __name__ == "__main__":
    main()
