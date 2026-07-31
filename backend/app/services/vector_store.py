import numpy as np
import faiss


class VectorStore:
    """FAISS-backed vector store for embedding similarity search."""

    def __init__(self, dimension: int) -> None:
        self._index = faiss.IndexFlatL2(dimension)
        self._embeddings: list[list[float]] = []
        self.documents: list[dict] = []

    def add_embeddings(self, embeddings: list[list[float]]) -> None:
        """Add embeddings to the index.

        Args:
            embeddings: The embedding vectors to add.
        """
        vectors = np.array(embeddings, dtype=np.float32)
        self._index.add(vectors)
        self._embeddings.extend(embeddings)

    def add_documents(self, texts: list[str], filename: str) -> None:
        """Store document chunks mapped to the FAISS index order.

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

    def search(
        self,
        query_embedding: list[float],
        k: int = 5,
    ) -> tuple[list[list[float]], list[list[int]]]:
        """Search the index for the closest embeddings to the query.

        Args:
            query_embedding: The query embedding vector.
            k: The number of nearest neighbors to return.

        Returns:
            A tuple of (distances, indices) for the nearest neighbors.
        """
        query = np.array([query_embedding], dtype=np.float32)
        distances, indices = self._index.search(query, k)
        return distances.tolist(), indices.tolist()
