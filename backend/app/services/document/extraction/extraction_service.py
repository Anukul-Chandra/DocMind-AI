"""Structured information extraction for classified documents.

The extraction layer consumes the existing provider-agnostic LLM Gateway
(:class:`app.services.llm.provider_manager.ProviderManager`) exactly like the
chat service does: it builds a system prompt that embeds the target document
type's JSON schema, calls ``ProviderManager.generate`` with a temperature of
zero for determinism, then parses and validates the returned text.

Malformed, empty, or non-JSON responses never raise: they produce a result
with a safe ``invalid``/``unavailable`` status and no extracted data, so an
indexing upload can never fail because of a bad extraction response. Unknown
documents are never forced through a known type's schema.
"""

import json
import re

from pydantic import BaseModel, ValidationError

from app.services.document.classifier import UNKNOWN
from app.services.document.extraction.schemas import SCHEMAS
from app.services.llm.provider_manager import LLMUnavailableError

#: Result statuses reported by the extraction layer.
EXTRACTED = "extracted"
SKIPPED = "skipped"
EMPTY = "empty"
INVALID = "invalid"
UNAVAILABLE = "unavailable"

#: Response text is capped so the provider's cost and latency stay bounded.
_DEFAULT_MAX_INPUT_CHARS = 20000
_DEFAULT_MAX_TOKENS = 1500

_FENCE_RE = re.compile(r"```(?:json)?\s*", re.IGNORECASE)
_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


class ExtractionResult:
    """Outcome of a single extraction attempt.

    Attributes:
        document_type: The classification the extraction was run for (always
            ``unknown`` for skipped documents).
        status: One of the module-level status constants.
        extracted: The validated structured data as a plain dict, or None.
        provider: The provider that produced the data, if any.
        model: The model that produced the data, if any.
        error: A human-readable description when extraction failed.
    """

    __slots__ = (
        "document_type",
        "status",
        "extracted",
        "provider",
        "model",
        "error",
    )

    def __init__(
        self,
        document_type: str,
        status: str,
        extracted: dict | None = None,
        provider: str = "",
        model: str = "",
        error: str = "",
    ) -> None:
        """Initialize an extraction result.

        Args:
            document_type: The classification the extraction ran for.
            status: The outcome status.
            extracted: The validated structured data, or None.
            provider: The provider that produced the data, if any.
            model: The model that produced the data, if any.
            error: A description of the failure, if any.
        """
        self.document_type = document_type
        self.status = status
        self.extracted = extracted
        self.provider = provider
        self.model = model
        self.error = error


class ExtractionService:
    """Extract structured JSON from cleaned document text.

    The service depends only on the provider-agnostic ``ProviderManager``
    interface it receives. It knows nothing about concrete providers: the same
    failover and rotation behavior used for chat is reused as-is.
    """

    def __init__(
        self,
        provider_manager,
        max_input_chars: int = _DEFAULT_MAX_INPUT_CHARS,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        """Initialize the extraction service with its LLM collaborator.

        Args:
            provider_manager: The provider-agnostic LLM Gateway used to request
                structured output.
            max_input_chars: Upper bound for the document text sent to the
                provider.
            max_tokens: Maximum number of tokens the provider may generate.
        """
        self._provider_manager = provider_manager
        self._max_input_chars = max_input_chars
        self._max_tokens = max_tokens

    async def extract(self, text: str, classification: str) -> ExtractionResult:
        """Extract structured data for a classified document.

        Args:
            text: The cleaned extracted document text.
            classification: The document type produced by the classifier.

        Returns:
            An ExtractionResult. Known types produce validated data when the
            provider responds with valid JSON; unknown types are skipped and
            never sent to the provider.
        """
        schema = SCHEMAS.get(classification)
        if schema is None:
            return ExtractionResult(document_type=classification, status=SKIPPED)
        if not text or not text.strip():
            return ExtractionResult(document_type=classification, status=EMPTY)

        system_prompt = self._build_system_prompt(classification, schema)
        prompt = self._build_document_prompt(text)

        try:
            response = await self._provider_manager.generate(
                prompt,
                system_prompt=system_prompt,
                temperature=0.0,
                max_tokens=self._max_tokens,
            )
        except LLMUnavailableError as exc:
            return ExtractionResult(
                document_type=classification,
                status=UNAVAILABLE,
                error=str(exc),
            )

        payload = self._parse_json(response.text)
        if payload is None:
            return ExtractionResult(
                document_type=classification,
                status=INVALID,
                provider=response.provider,
                model=response.model,
                error="the provider returned no parseable JSON object",
            )

        try:
            validated = schema.model_validate(payload)
        except ValidationError as exc:
            return ExtractionResult(
                document_type=classification,
                status=INVALID,
                provider=response.provider,
                model=response.model,
                error=f"extraction did not match the schema: {exc}",
            )

        return ExtractionResult(
            document_type=classification,
            status=EXTRACTED,
            extracted=validated.model_dump(),
            provider=response.provider,
            model=response.model,
        )

    @staticmethod
    def _build_system_prompt(classification: str, schema: type[BaseModel]) -> str:
        """Build the system prompt embedding the target JSON schema.

        Args:
            classification: The document type being extracted.
            schema: The pydantic model describing the target fields.

        Returns:
            The system prompt instructing the model to emit only JSON.
        """
        json_schema = schema.model_json_schema()
        fields = ", ".join(sorted(json_schema.get("properties", {})))
        return (
            "You are a document data extraction engine.\n"
            f"The document is classified as a '{classification}'.\n"
            "Extract the following fields from the document text: "
            f"{fields}.\n"
            "Return a single JSON object matching this schema:\n"
            f"{json.dumps(json_schema)}\n"
            "Return ONLY the JSON object. No markdown, no commentary, no "
            "explanations, no trailing text."
        )

    def _build_document_prompt(self, text: str) -> str:
        """Build the user prompt containing the document text.

        Args:
            text: The cleaned extracted document text.

        Returns:
            The user prompt with the bounded document text.
        """
        bounded = text[: self._max_input_chars]
        return f"Document text:\n\n{bounded}"

    @staticmethod
    def _parse_json(text: str) -> dict | None:
        """Parse model output into a plain dict, tolerating markdown fences.

        Args:
            text: The raw model output.

        Returns:
            A parsed dict, or None if the output is not a JSON object.
        """
        stripped = _FENCE_RE.sub("", text.strip()).rstrip("`").strip()
        try:
            data = json.loads(stripped)
        except (ValueError, TypeError):
            match = _OBJECT_RE.search(stripped)
            if not match:
                return None
            try:
                data = json.loads(match.group(0))
            except (ValueError, TypeError):
                return None
        if not isinstance(data, dict):
            return None
        return data