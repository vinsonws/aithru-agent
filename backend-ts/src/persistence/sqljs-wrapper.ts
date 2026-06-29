/**
 * Thin adapter that wraps sql.js Database to satisfy Kysely's SqliteDatabase
 * interface. Used as the drop-in when better-sqlite3 native binaries are
 * unavailable.
 */
import type { Database as SqlJsDb, Statement as SqlJsStmt } from "sql.js";

const READER_PREFIX_RE = /^\s*(SELECT|PRAGMA|EXPLAIN|DESCRIBE|WITH|VALUES\s*\()/i;

export class SqlJsToKyselyAdapter {
  readonly #db: SqlJsDb;

  constructor(db: SqlJsDb) {
    this.#db = db;
  }

  /** Kysely-required: close the underlying database. */
  close(): void {
    this.#db.close();
  }

  /**
   * Kysely-required: prepare a statement and return an object with
   * `reader` / `all` / `run` / `iterate` matching the better-sqlite3 shape.
   */
  prepare(sql: string) {
    const stmt: SqlJsStmt = this.#db.prepare(sql);
    const isReader = READER_PREFIX_RE.test(sql.trim());
    const db = this.#db;

    return {
      reader: isReader,

      all(parameters: ReadonlyArray<unknown>): unknown[] {
        if (parameters.length > 0) stmt.bind(parameters as any);
        const rows: unknown[] = [];
        while (stmt.step()) rows.push(stmt.getAsObject());
        stmt.reset();
        return rows;
      },

      run(parameters: ReadonlyArray<unknown>) {
        if (parameters.length > 0) stmt.bind(parameters as any);
        stmt.step();
        const changes = db.getRowsModified();
        stmt.reset();
        return { changes, lastInsertRowid: 0 };
      },

      iterate(parameters: ReadonlyArray<unknown>): IterableIterator<unknown> {
        if (parameters.length > 0) stmt.bind(parameters as any);
        const self = {
          next(): IteratorResult<unknown> {
            if (stmt.step()) return { value: stmt.getAsObject(), done: false };
            stmt.reset();
            return { value: undefined, done: true };
          },
          [Symbol.iterator]() {
            return this;
          },
        };
        return self as IterableIterator<unknown>;
      },
    };
  }

  // ── Additional helpers used directly by migrations & store ──────────

  /** Execute raw SQL (for DDL / PRAGMA statements). */
  exec(sql: string): void {
    this.#db.run(sql);
  }

  /** Return number of rows modified by the last statement. */
  getRowsModified(): number {
    return this.#db.getRowsModified();
  }

  /** Return the raw sql.js Database for direct operations. */
  raw(): SqlJsDb {
    return this.#db;
  }
}
