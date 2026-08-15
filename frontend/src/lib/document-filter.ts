export type DocumentType =
  | "resume"
  | "invoice"
  | "receipt"
  | "passport"
  | "form"
  | "unknown";

export type DocumentTypeFilter = DocumentType | "all";

export interface DocumentFilters {
  query: string;
  type: DocumentTypeFilter;
}

export interface DocumentFilterable {
  filename: string;
  classification: string;
}

export const NO_TYPE_FILTER: DocumentTypeFilter = "all";

export function normalizeQuery(query: string): string {
  return query.trim().toLowerCase();
}

export function matchesQuery(
  document: DocumentFilterable,
  query: string,
): boolean {
  const normalized = normalizeQuery(query);
  if (normalized === "") return true;
  return document.filename.toLowerCase().includes(normalized);
}

export function matchesType(
  document: DocumentFilterable,
  type: DocumentTypeFilter,
): boolean {
  if (type === NO_TYPE_FILTER) return true;
  return document.classification === type;
}

export function hasActiveFilters(filters: DocumentFilters): boolean {
  return (
    normalizeQuery(filters.query) !== "" || filters.type !== NO_TYPE_FILTER
  );
}

export function filterDocuments<T extends DocumentFilterable>(
  documents: readonly T[],
  filters: DocumentFilters,
): T[] {
  return documents.filter(
    (document) =>
      matchesQuery(document, filters.query) &&
      matchesType(document, filters.type),
  );
}
