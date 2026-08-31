import os

from app.core.config import settings

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


class EmbeddingService:
    """Generate embeddings for text using a sentence-transformer model."""

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        import torch

        torch.set_num_threads(1)
        torch.set_grad_enabled(False)
        self._model = SentenceTransformer(settings.embedding_model)

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for all input texts.

        Args:
            texts: The texts to embed.

        Returns:
            A list of embedding vectors, one per input text.
        """
        return self._model.encode(texts).tolist()

    def get_embedding_dimension(self) -> int:
        """Return the dimension of the embedding vectors produced by the model.

        Returns:
            The number of dimensions in each embedding vector.
        """
        return self._model.get_embedding_dimension()
