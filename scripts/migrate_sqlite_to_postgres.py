#!/usr/bin/env python3
"""Migra dados do SQLite local para o PostgreSQL (Render/Azure/etc.)."""

import os
import sqlite3
from typing import List

import psycopg2
from psycopg2 import sql


TABLE_ORDER: List[str] = [
    "usuarios",
    "processos",
    "movimentacoes",
    "campos_extra",
    "notificacoes",
    "importacoes_temp",
]


def normalize_database_url(raw: str) -> str:
    url = (raw or "").strip()
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def q_ident(name: str) -> sql.Identifier:
    return sql.Identifier(name)


def fetch_columns_sqlite(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]


def copy_table(sqlite_conn: sqlite3.Connection, pg_conn, table: str) -> int:
    columns = fetch_columns_sqlite(sqlite_conn, table)
    if not columns:
        return 0

    col_idents = [q_ident(c) for c in columns]
    select_sql = f"SELECT {', '.join(columns)} FROM {table}"
    rows = sqlite_conn.execute(select_sql).fetchall()
    if not rows:
        return 0

    with pg_conn.cursor() as cur:
        placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in columns)
        insert_stmt = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            q_ident(table),
            sql.SQL(", ").join(col_idents),
            placeholders,
        )
        cur.executemany(insert_stmt.as_string(pg_conn), rows)
    return len(rows)


def reset_sequences(pg_conn, table: str) -> None:
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1
              FROM information_schema.columns
              WHERE table_schema = 'public'
                AND table_name = %s
                AND column_name = 'id'
            )
            """,
            (table,),
        )
        has_id = bool(cur.fetchone()[0])
        if not has_id:
            return
        cur.execute(
            sql.SQL(
                """
                SELECT setval(
                    pg_get_serial_sequence(%s, 'id'),
                    COALESCE((SELECT MAX(id) FROM {}), 1),
                    true
                )
                """
            ).format(q_ident(table)),
            (f"public.{table}",),
        )


def main() -> None:
    sqlite_path = os.environ.get("SQLITE_PATH", "controle_processos.db")
    database_url = normalize_database_url(os.environ.get("DATABASE_URL", ""))
    truncate_first = (os.environ.get("TRUNCATE_FIRST", "1").strip().lower() in {"1", "true", "yes", "on"})

    if not database_url:
        raise SystemExit("DATABASE_URL nao informado.")
    if not os.path.exists(sqlite_path):
        raise SystemExit(f"SQLite nao encontrado: {sqlite_path}")

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    pg_conn = psycopg2.connect(database_url)
    pg_conn.autocommit = False

    try:
        with pg_conn.cursor() as cur:
            cur.execute("SET session_replication_role = replica;")
            if truncate_first:
                cur.execute(
                    "TRUNCATE TABLE "
                    + ", ".join(f'"{t}"' for t in TABLE_ORDER)
                    + " RESTART IDENTITY CASCADE"
                )

        total = 0
        for table in TABLE_ORDER:
            inserted = copy_table(sqlite_conn, pg_conn, table)
            total += inserted
            print(f"{table}: {inserted} registros")

        with pg_conn.cursor() as cur:
            for table in TABLE_ORDER:
                reset_sequences(pg_conn, table)
            cur.execute("SET session_replication_role = origin;")

        pg_conn.commit()
        print(f"Migracao concluida. Total de linhas inseridas: {total}")
    except Exception:
        pg_conn.rollback()
        raise
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
