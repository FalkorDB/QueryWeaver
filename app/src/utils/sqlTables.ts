/**
 * Lightweight SQL table extraction.
 *
 * Pulls the table names referenced by a generated SQL query so the schema
 * canvas can highlight the tables (and the relations between them) the query
 * actually touches. This is intentionally a heuristic scanner — it does not
 * aim to be a full SQL parser.
 */

// Keywords that may directly follow FROM/JOIN/... and must never be treated
// as a table name or as a table alias.
const RESERVED = new Set([
  'select', 'from', 'where', 'group', 'order', 'having', 'limit', 'offset',
  'union', 'intersect', 'except', 'join', 'inner', 'left', 'right', 'full',
  'cross', 'outer', 'natural', 'lateral', 'on', 'using', 'as', 'and', 'or',
  'not', 'set', 'values', 'returning', 'with', 'distinct', 'into', 'window',
  'fetch', 'for', 'exists', 'case', 'when', 'then', 'else', 'end',
]);

// Optionally-qualified identifier: schema."table", `db`.`table`, [dbo].[table]
const IDENTIFIER =
  '(?:[A-Za-z_][\\w$]*|"[^"]*"|`[^`]*`|\\[[^\\]]*\\])' +
  '(?:\\s*\\.\\s*(?:[A-Za-z_][\\w$]*|"[^"]*"|`[^`]*`|\\[[^\\]]*\\]))*';

const unquote = (identifier: string): string =>
  identifier.replace(/^["`[]/, '').replace(/["`\]]$/, '');

/** Keep only the table part of a qualified name (`public.users` → `users`). */
const tableName = (qualified: string): string => {
  const parts = qualified.split('.').map((part) => unquote(part.trim()));
  return parts[parts.length - 1] ?? '';
};

/** Names introduced by `WITH <name> AS (...)` — they are not real tables. */
const collectCteNames = (sql: string): Set<string> => {
  const names = new Set<string>();
  const re = /\b([A-Za-z_][\w$]*)\s+AS\s*\(/gi;
  let match: RegExpExecArray | null;
  while ((match = re.exec(sql)) !== null) {
    names.add(match[1].toLowerCase());
  }
  return names;
};

/**
 * Extracts the table names referenced by a SQL statement.
 * Returns unique names in the order they appear.
 */
export const extractTablesFromSQL = (sql: string): string[] => {
  if (!sql || !sql.trim()) return [];

  // Drop comments and string literals so they cannot produce false matches.
  const cleaned = sql
    .replace(/--[^\n]*/g, ' ')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/'(?:''|[^'])*'/g, "''");

  const cteNames = collectCteNames(cleaned);
  const tables: string[] = [];
  const seen = new Set<string>();

  const add = (qualified: string) => {
    const name = tableName(qualified);
    const key = name.toLowerCase();
    if (!name || RESERVED.has(key) || cteNames.has(key) || seen.has(key)) return;
    seen.add(key);
    tables.push(name);
  };

  const keywordRe = /\b(from|join|update|into)\b/gi;
  const referenceRe = new RegExp(`^\\s*(${IDENTIFIER})`, 'i');
  const aliasRe = /^\s+(?:as\s+)?([A-Za-z_][\w$]*)/i;

  let keyword: RegExpExecArray | null;
  while ((keyword = keywordRe.exec(cleaned)) !== null) {
    // Only `FROM` accepts a comma-separated list of tables.
    const acceptsList = keyword[1].toLowerCase() === 'from';
    let index = keywordRe.lastIndex;

    for (;;) {
      const reference = cleaned.slice(index).match(referenceRe);
      // A subquery or unexpected token — the inner FROM is picked up separately.
      if (!reference) break;

      index += reference[0].length;
      add(reference[1]);

      if (!acceptsList) break;

      const alias = cleaned.slice(index).match(aliasRe);
      if (alias && !RESERVED.has(alias[1].toLowerCase())) {
        index += alias[0].length;
      }

      const comma = cleaned.slice(index).match(/^\s*,/);
      if (!comma) break;
      index += comma[0].length;
    }
  }

  return tables;
};
