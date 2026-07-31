from sentence_transformers import SentenceTransformer

from app.core.config import settings


class EmbeddingService:
    """Generate embeddings for text using a sentence-transformer model."""

    def __init__(self) -> None:
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
