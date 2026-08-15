// Focused regression verification for the client-side document search/filter
// logic (filename search + classification filter + combined + empty results).
//
// The pure functions live in src/lib/document-filter.ts and are dependency
// free, so Node can run them directly via type stripping:
//
//   node --experimental-strip-types scripts/test-document-filter.mts
//
// Exit status is non-zero if any check fails.

import {
  filterDocuments,
  hasActiveFilters,
  matchesQuery,
  matchesType,
  normalizeQuery,
  NO_TYPE_FILTER,
} from "../src/lib/document-filter.ts";

const DOCS = [
  { document_id: "1", filename: "invoice-report.pdf", classification: "invoice" },
  { document_id: "2", filename: "Invoice_FINAL.pdf", classification: "invoice" },
  { document_id: "3", filename: "resume.pdf", classification: "resume" },
  { document_id: "4", filename: "receipt.pdf", classification: "receipt" },
  { document_id: "5", filename: "meeting notes.txt.pdf", classification: "unknown" },
  { document_id: "6", filename: "passport.pdf", classification: "passport" },
];

const checks = [];

function check(name, passed, detail = "") {
  checks.push({ name, passed, detail });
}

function ids(docs) {
  return docs.map((doc) => doc.document_id).sort().join(",");
}

// 1. History: no filters returns every document.
check(
  "1. no filters returns the full history",
  ids(filterDocuments(DOCS, { query: "", type: NO_TYPE_FILTER })) ===
    "1,2,3,4,5,6",
);

// 2. Filename search: case-insensitive substring on the filename.
check(
  "2. filename search finds matching documents",
  ids(filterDocuments(DOCS, { query: "invoice", type: NO_TYPE_FILTER })) ===
    "1,2",
);
check(
  "2. filename search is case-insensitive",
  ids(filterDocuments(DOCS, { query: "RESUME", type: NO_TYPE_FILTER })) ===
    "3",
);
check(
  "2. filename search trims surrounding whitespace",
  ids(filterDocuments(DOCS, { query: "  receipt  ", type: NO_TYPE_FILTER })) ===
    "4",
);
check(
  "2. filename search matches substrings inside names",
  ids(filterDocuments(DOCS, { query: "notes", type: NO_TYPE_FILTER })) === "5",
);
check(
  "2. no filename match returns empty",
  filterDocuments(DOCS, { query: "taxes", type: NO_TYPE_FILTER }).length === 0,
);

// 3. Classification filter: exact type match.
check(
  "3. type filter returns only that type",
  ids(filterDocuments(DOCS, { query: "", type: "invoice" })) === "1,2",
);
check(
  "3. unknown type filter returns unknown documents",
  ids(filterDocuments(DOCS, { query: "", type: "unknown" })) === "5",
);
check(
  "3. no documents of a type returns empty",
  filterDocuments(DOCS, { query: "", type: "form" }).length === 0,
);

// 4. Search + type filter can be combined.
check(
  "4. combined search and type filter intersect",
  ids(filterDocuments(DOCS, { query: "invoice", type: "invoice" })) === "1,2",
);
check(
  "4. combined filter returns empty when disjoint",
  filterDocuments(DOCS, { query: "resume", type: "invoice" }).length === 0,
);

// 5. Empty results handled: filtered list is empty, filters stay active.
check(
  "5. empty result set has zero entries",
  filterDocuments(DOCS, { query: "zzz", type: "invoice" }).length === 0,
);
check(
  "5. active filters are detected",
  hasActiveFilters({ query: "zzz", type: NO_TYPE_FILTER }) === true &&
    hasActiveFilters({ query: "", type: "invoice" }) === true,
);
check(
  "5. default filters are not active",
  hasActiveFilters({ query: "", type: NO_TYPE_FILTER }) === false,
);

// Matchers are consistent with the composed behavior.
check(
  "6. matchesQuery matches a single document",
  matchesQuery(DOCS[0], "invoice-report") === true &&
    matchesQuery(DOCS[0], "resume") === false,
);
check(
  "6. matchesType matches the exact classification",
  matchesType(DOCS[0], "invoice") === true &&
    matchesType(DOCS[0], "resume") === false &&
    matchesType(DOCS[0], NO_TYPE_FILTER) === true,
);
check(
  "6. normalizeQuery trims and lowercases",
  normalizeQuery("  InVoIcE  ") === "invoice",
);

let failed = 0;
for (const { name, passed, detail } of checks) {
  const status = passed ? "PASS" : "FAIL";
  if (!passed) failed += 1;
  console.log(`${name.padEnd(58)}${status}`);
  if (!passed && detail) console.log(`  ${detail}`);
}

console.log("\n" + (failed === 0 ? "PASS" : `FAIL (${failed}/${checks.length})`));
process.exit(failed === 0 ? 0 : 1);
