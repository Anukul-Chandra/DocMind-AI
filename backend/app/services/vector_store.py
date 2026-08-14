import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import faiss


@dataclass(frozen=True)
class IndexSnapshot:
    """An immutable copy of a VectorStore's index state.

    The FAISS index is deep-cloned so it never shares vectors with the live
    store; the embeddings mirror is stored as immutable tuples to keep the
    snapshot safe to reuse.

    Attributes:
        index: A deep clone of the FAISS index (contents and ordering).
        embeddings: An immutable copy of the raw embedding list.
    """

    index: object
    embeddings: tuple[tuple[float, ...], ...]


class VectorStore:
    """FAISS-backed vector store for embedding similarity search."""

    def __init__(self, dimension: int) -> None:
        self._index = faiss.IndexFlatL2(dimension)
        self._embeddings: list[list[float]] = []
        self.documents: list[dict] = []

    @property
    def ntotal(self) -> int:
        """Return the number of vectors currently in the FAISS index.

        Returns:
            The total count of vectors in the underlying index.
        """
        return self._index.ntotal

    def add_embeddings(self, embeddings: list[list[float]]) -> None:
        """Add embeddings to the index.

        Args:
            embeddings: The embedding vectors to add.
        """
        vectors = np.array(embeddings, dtype=np.float32)
        self._index.add(vectors)
        self._embeddings.extend(embeddings)

    def snapshot_state(self) -> IndexSnapshot:
        """Capture the current index state as an independent snapshot.

        The FAISS index is deep-cloned, so later changes to this store never
        affect the returned snapshot, and later changes to the snapshot never
        affect this store.

        Returns:
            An IndexSnapshot preserving the current contents and ordering.
        """
        return IndexSnapshot(
            index=faiss.clone_index(self._index),
            embeddings=tuple(tuple(vector) for vector in self._embeddings),
        )

    def restore_state(self, snapshot: IndexSnapshot) -> None:
        """Restore a previously captured index state exactly.

        The snapshot is cloned on restore so the original snapshot object is
        never mutated by subsequent operations on this store.

        Args:
            snapshot: An IndexSnapshot captured earlier from this store.
        """
        self._index = faiss.clone_index(snapshot.index)
        self._embeddings = [list(vector) for vector in snapshot.embeddings]

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

    def save(self, path: str) -> None:
        """Persist the FAISS index to disk atomically.

        The index is written to a unique temporary file in the same directory
        as the target, fully written and synced, then moved over the target
        with :func:`os.replace` so a crash or failed write never leaves a
        partially written ``index.faiss``. If anything fails, the temporary
        file is removed and the previous target file is left untouched.

        Args:
            path: The file path to save the index to.

        Raises:
            The underlying exception from the failing write step; the target
            index is never replaced with a partial file.
        """
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
        )
        os.close(fd)
        try:
            faiss.write_index(self._index, tmp_name)
            with open(tmp_name, "r+b") as f:
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, target)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def load_index(self, path: str) -> None:
        """Load a FAISS index into this store from disk.

        Args:
            path: The file path to load the index from.
        """
        if os.path.exists(path):
            self._index = faiss.read_index(path)

    @classmethod
    def load(cls, path: str, dimension: int) -> "VectorStore":
        """Load a FAISS index from disk, or create an empty one if missing.

        Args:
            path: The file path to load the index from.
            dimension: The embedding dimension for a new empty index.

        Returns:
            A VectorStore instance backed by the loaded index.
        """
        store = cls(dimension)
        store.load_index(path)
        return store
