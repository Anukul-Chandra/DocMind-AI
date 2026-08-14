import { FileText } from "lucide-react";

interface ScanCardProps {
  label: string;
}

export function ScanCard({ label }: ScanCardProps) {
  return (
    <div
      className="flex flex-col items-center gap-4 rounded-xl border bg-card/40 px-6 py-10 text-center"
      role="status"
      aria-label={label}
    >
      <div className="relative w-40 overflow-hidden rounded-md border bg-white p-4 shadow-sm">
        <div className="space-y-2" aria-hidden="true">
          <div className="h-2 w-3/4 rounded bg-slate-200" />
          <div className="h-2 w-full rounded bg-slate-100" />
          <div className="h-2 w-5/6 rounded bg-slate-100" />
          <div className="h-2 w-full rounded bg-slate-100" />
          <div className="h-2 w-2/3 rounded bg-slate-100" />
        </div>
        <div className="docmind-scan absolute inset-x-0 top-0 h-1 rounded-full bg-gradient-to-r from-transparent via-sky-500 to-transparent shadow-[0_0_10px_1px_rgba(14,165,233,0.7)]" />
      </div>
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <FileText className="size-4" aria-hidden="true" />
        <span>{label}</span>
      </div>
    </div>
  );
}