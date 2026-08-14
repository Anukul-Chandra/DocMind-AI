import { UploadCloud } from "lucide-react";

import { PageHeader } from "@/components/app/PageHeader";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export function DocumentsPage() {
  return (
    <div className="mx-auto w-full max-w-6xl space-y-6 p-6 lg:p-8">
      <PageHeader
        title="Documents"
        description="Upload, manage, and delete your PDF documents."
      />
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Your documents</CardTitle>
          <CardDescription>
            Uploaded documents will appear here.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col items-center justify-center gap-3 py-12 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-muted">
            <UploadCloud className="size-6 text-muted-foreground" aria-hidden="true" />
          </span>
          <p className="text-sm text-muted-foreground">
            Document management is coming in the next phase.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
