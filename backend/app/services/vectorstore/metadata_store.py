class MetadataStore:
    """Store document chunk metadata in the order they are added."""

    def __init__(self) -> None:
        self.documents: list[dict] = []

    def add_documents(self, texts: list[str], filename: str) -> None:
        """Store document chunks with sequential ids.

        Args:
            texts: The document text chunks.
            filename: The source document's filename.
        """
        start_id = len(self.documents)
        for offset, text in enumerate(texts):
            self.documents.append(
                {
                    "id": start_id + offset,
                    "text": text,
                    "filename": filename,
                }
            )

    def get_document(self, index: int) -> dict:
        """Return the stored document for a given index.

        Args:
            index: The index of the stored document.

        Returns:
            The stored document.
        """
        return self.documents[index]
