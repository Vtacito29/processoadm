#!/usr/bin/env python3
"""
Migra dados de um banco SQLite para PostgreSQL em lotes pequenos.

Uso rapido:
  python scripts/migrate_sqlite_to_postgres.py --sqlite controle_processos.db --postgres "$env:DATABASE_URL" --truncate --batch-size 500
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from typing import Dict, Iterable, List, Sequence, Tuple
from urllib.parse import urlparse

import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json, execute_values


def normalize_postgres_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def sqlite_tables(conn: sqlite3.Connection) -> List[str]:
    cur = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    )
    return [r[0] for r in cur.fetchall()]


def postgres_tables(conn) -> set:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            """
        )
        return {r[0] for r in cur.fetchall()}


def sqlite_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.execute(f'PRAGMA table_info("{table}")')
    return [r[1] for r in cur.fetchall()]


def postgres_column_types(conn, table: str) -> Dict[str, str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table,),
        )
        return {r[0]: r[1] for r in cur.fetchall()}


def normalize_value(value, pg_type: str):
    if value is None:
        return None

    if pg_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            v = value.strip().lower()
            if v in {"1", "true", "t", "yes", "y", "on"}:
                return True
            if v in {"0", "false", "f", "no", "n", "off"}:
                return False
        return value

    if pg_type in {"json", "jsonb"}:
        if isinstance(value, (dict, list)):
            return Json(value)
        if isinstance(value, str):
            txt = value.strip()
            if not txt:
                return Json(None)
            try:
                return Json(json.loads(txt))
            except Exception:
                return Json(value)
        return Json(value)

    return value


def truncate_tables(conn, tables: Sequence[str]) -> None:
    if not tables:
        return
    identifiers = [sql.Identifier(t) for t in tables]
    stmt = sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(
        sql.SQL(", ").join(identifiers)
    )
    with conn.cursor() as cur:
        cur.execute(stmt)
    conn.commit()


def reset_serial_sequences(conn, tables: Iterable[str]) -> None:
    with conn.cursor() as cur:
        for table in tables:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                  AND column_default LIKE 'nextval%%'
                """,
                (table,),
            )
            cols = [r[0] for r in cur.fetchall()]
            for col in cols:
                cur.execute(
                    "SELECT pg_get_serial_sequence(%s, %s)",
                    (f"public.{table}", col),
                )
                seq = cur.fetchone()[0]
                if not seq:
                    continue
                cur.execute(
                    sql.SQL(
                        "SELECT setval(%s, COALESCE((SELECT MAX({col}) FROM {tbl}), 1), true)"
                    ).format(col=sql.Identifier(col), tbl=sql.Identifier(table)),
                    (seq,),
                )
    conn.commit()


def migrate_table(
    sqlite_conn: sqlite3.Connection,
    pg_conn,
    table: str,
    batch_size: int,
) -> Tuple[int, int]:
    src_cols = sqlite_columns(sqlite_conn, table)
    pg_types = postgres_column_types(pg_conn, table)
    cols = [c for c in src_cols if c in pg_types]

    if not cols:
        return 0, 0

    copied = 0
    skipped = 0

    q_cols = ", ".join([f'"{c}"' for c in cols])
    src_cur = sqlite_conn.execute(f'SELECT {q_cols} FROM "{table}"')

    insert_stmt = sql.SQL("INSERT INTO {tbl} ({cols}) VALUES %s").format(
        tbl=sql.Identifier(table),
        cols=sql.SQL(", ").join(sql.Identifier(c) for c in cols),
    )

    with pg_conn.cursor() as pg_cur:
        while True:
            rows = src_cur.fetchmany(batch_size)
            if not rows:
                break

            normalized_rows = []
            for row in rows:
                norm = []
                for idx, value in enumerate(row):
                    col = cols[idx]
                    pg_type = pg_types[col]
                    norm.append(normalize_value(value, pg_type))
                normalized_rows.append(tuple(norm))

            try:
                execute_values(pg_cur, insert_stmt.as_string(pg_conn), normalized_rows)
                copied += len(normalized_rows)
                pg_conn.commit()
            except Exception as exc:
                pg_conn.rollback()
                skipped += len(normalized_rows)
                print(
                    f"[ERRO] tabela={table} lote={len(normalized_rows)} ignorado: {exc}",
                    file=sys.stderr,
                )

    return copied, skipped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrar SQLite para PostgreSQL em lotes."
    )
    parser.add_argument(
        "--sqlite",
        default="controle_processos.db",
        help="Caminho do SQLite de origem.",
    )
    parser.add_argument(
        "--postgres",
        required=True,
        help="DATABASE_URL do PostgreSQL de destino.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Linhas por lote (use 100-500 em maquina fraca).",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Apaga as tabelas de destino antes de migrar.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.batch_size <= 0:
        print("--batch-size deve ser maior que 0.", file=sys.stderr)
        return 2

    sqlite_conn = sqlite3.connect(args.sqlite)
    sqlite_conn.row_factory = sqlite3.Row

    pg_url = normalize_postgres_url(args.postgres.strip())
    parsed = urlparse(pg_url)
    if parsed.scheme not in {"postgresql", "postgres"}:
        print("URL de PostgreSQL invalida.", file=sys.stderr)
        return 2

    pg_conn = psycopg2.connect(pg_url)

    try:
        src_tables = sqlite_tables(sqlite_conn)
        dst_tables = postgres_tables(pg_conn)
        common_tables = [t for t in src_tables if t in dst_tables]

        if not common_tables:
            print("Nenhuma tabela em comum entre SQLite e PostgreSQL.", file=sys.stderr)
            return 1

        print(f"Tabelas encontradas: {', '.join(common_tables)}")

        if args.truncate:
            print("Limpando tabelas de destino (TRUNCATE ... CASCADE).")
            truncate_tables(pg_conn, common_tables)

        total_copied = 0
        total_skipped = 0
        for table in common_tables:
            copied, skipped = migrate_table(
                sqlite_conn=sqlite_conn,
                pg_conn=pg_conn,
                table=table,
                batch_size=args.batch_size,
            )
            total_copied += copied
            total_skipped += skipped
            print(f"[OK] {table}: copiados={copied} ignorados={skipped}")

        reset_serial_sequences(pg_conn, common_tables)
        print(
            f"Concluido. Total copiados={total_copied} | total ignorados={total_skipped}"
        )
        return 0
    finally:
        try:
            sqlite_conn.close()
        except Exception:
            pass
        try:
            pg_conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())

