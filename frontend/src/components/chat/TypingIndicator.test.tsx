import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { TypingIndicator, type IndicatorCategory } from "./TypingIndicator";

describe("TypingIndicator", () => {
  it("shows 'Thinking…' for general category", () => {
    render(<TypingIndicator category="general" />);
    expect(screen.getByText("Thinking…")).toBeInTheDocument();
  });

  it("shows document-analysis text for document category", () => {
    render(<TypingIndicator category="document" />);
    expect(screen.getByText("Analyzing your indexed documents…")).toBeInTheDocument();
  });

  it("shows 'Checking your documents…' for metadata category", () => {
    render(<TypingIndicator category="metadata" />);
    expect(screen.getByText("Checking your documents…")).toBeInTheDocument();
  });

  it("defaults to general category when no category prop provided", () => {
    render(<TypingIndicator />);
    expect(screen.getByText("Thinking…")).toBeInTheDocument();
  });

  it("shows 'Processing image…' when hasImages is true and category is general", () => {
    render(<TypingIndicator category="general" hasImages />);
    expect(screen.getByText("Processing image…")).toBeInTheDocument();
  });

  it("shows document text even when hasImages is true for document category", () => {
    render(<TypingIndicator category="document" hasImages />);
    expect(screen.getByText("Analyzing your indexed documents…")).toBeInTheDocument();
  });

  it("does NOT show document-analysis text for general category", () => {
    render(<TypingIndicator category="general" />);
    expect(screen.queryByText("Analyzing your indexed documents…")).not.toBeInTheDocument();
  });

  it("does NOT show document-analysis text for metadata category", () => {
    render(<TypingIndicator category="metadata" />);
    expect(screen.queryByText("Analyzing your indexed documents…")).not.toBeInTheDocument();
  });

  it("does NOT show document-analysis text for image-only query", () => {
    render(<TypingIndicator category="general" hasImages />);
    expect(screen.queryByText("Analyzing your indexed documents…")).not.toBeInTheDocument();
  });

  it("always shows the DocMind label", () => {
    const categories: IndicatorCategory[] = ["general", "document", "metadata"];
    for (const cat of categories) {
      const { unmount } = render(<TypingIndicator category={cat} />);
      expect(screen.getByText("DocMind")).toBeInTheDocument();
      expect(screen.getByText("Processing")).toBeInTheDocument();
      unmount();
    }
  });

  it("sets correct aria-label for general category", () => {
    render(<TypingIndicator category="general" />);
    expect(screen.getByRole("status")).toHaveAttribute(
      "aria-label",
      "DocMind is thinking",
    );
  });

  it("sets correct aria-label for document category", () => {
    render(<TypingIndicator category="document" />);
    expect(screen.getByRole("status")).toHaveAttribute(
      "aria-label",
      "DocMind is analyzing your documents and composing an answer",
    );
  });

  it("sets correct aria-label for metadata category", () => {
    render(<TypingIndicator category="metadata" />);
    expect(screen.getByRole("status")).toHaveAttribute(
      "aria-label",
      "DocMind is checking your documents",
    );
  });

  it("sets correct aria-label for image processing", () => {
    render(<TypingIndicator category="general" hasImages />);
    expect(screen.getByRole("status")).toHaveAttribute(
      "aria-label",
      "DocMind is processing an image",
    );
  });

  it("no keyword-based frontend classifier is introduced (general text never leaks into document state)", () => {
    const { unmount } = render(<TypingIndicator category="document" />);
    expect(screen.queryByText("Thinking…")).not.toBeInTheDocument();
    unmount();

    const { unmount: unmount2 } = render(<TypingIndicator category="general" />);
    expect(screen.queryByText("Analyzing your indexed documents…")).not.toBeInTheDocument();
    unmount2();
  });
});
