import type { DocumentType } from "@/lib/document-filter";

export const DOCUMENT_TYPES: readonly DocumentType[] = [
  "resume",
  "invoice",
  "receipt",
  "passport",
  "form",
  "unknown",
];

const TYPE_LABELS: Record<string, string> = {
  resume: "Resume",
  invoice: "Invoice",
  receipt: "Receipt",
  passport: "Passport",
  form: "Form",
  unknown: "Unknown",
};

export function documentTypeLabel(type: string): string {
  return TYPE_LABELS[type] ?? "Document";
}