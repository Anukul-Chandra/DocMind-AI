import { FileText, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";

export function HomePage() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 p-8">
      <div className="flex items-center gap-2 text-2xl font-semibold">
        <FileText className="size-6" aria-hidden="true" />
        DocMind AI
      </div>
      <p className="text-sm text-muted-foreground">
        Phase 8 foundation is up and running.
      </p>
      <div className="flex items-center gap-2">
        <Button>Get started</Button>
        <Button variant="outline">
          <Sparkles className="size-4" aria-hidden="true" />
          Powered by RAG
        </Button>
      </div>
    </main>
  );
}
