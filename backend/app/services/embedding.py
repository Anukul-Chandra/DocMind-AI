from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"


class EmbeddingService:
    """Generate embeddings for text using a sentence-transformer model."""

    def __init__(self) -> None:
        self._model = SentenceTransformer(MODEL_NAME)

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for all input texts.

        Args:
            texts: The texts to embed.

        Returns:
            A list of embedding vectors, one per input text.
        """
        return self._model.encode(texts).tolist()
