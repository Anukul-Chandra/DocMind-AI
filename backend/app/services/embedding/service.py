import os
import time
import logging

from app.core.config import settings

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

_log = logging.getLogger(__name__)


class EmbeddingService:
    """Generate embeddings for text using a sentence-transformer model."""

    def __init__(self) -> None:
        _t = lambda: time.strftime("%H:%M:%S")
        _log.info("[%s] (diag) EmbeddingService.__init__ start", _t())

        from sentence_transformers import SentenceTransformer
        _log.info("[%s] (diag) sentence_transformers imported inside __init__", _t())

        import torch
        _log.info("[%s] (diag) torch imported inside __init__", _t())

        torch.set_num_threads(1)
        torch.set_grad_enabled(False)

        _log.info("[%s] (diag) Loading SentenceTransformer model '%s' …", _t(), settings.embedding_model)
        self._model = SentenceTransformer(settings.embedding_model)
        _log.info("[%s] (diag) SentenceTransformer model loaded OK", _t())

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
