export function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5" aria-label="DocMind is thinking">
      {[0, 1, 2].map((index) => (
        <span
          key={index}
          className="size-2 animate-bounce rounded-full bg-muted-foreground"
          style={{ animationDelay: `${index * 0.15}s` }}
        />
      ))}
    </div>
  );
}