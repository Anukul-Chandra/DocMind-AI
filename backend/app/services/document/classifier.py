"""Rule-based document type classification for the indexing pipeline."""

import re

UNKNOWN = "unknown"
RESUME = "resume"
INVOICE = "invoice"
RECEIPT = "receipt"
PASSPORT = "passport"
FORM = "form"

#: Supported V1 document types, in evaluation order.
SUPPORTED_TYPES = (RESUME, INVOICE, RECEIPT, PASSPORT, FORM)

#: Per-type (strong, weak) signal tuples. Strong signals are highly
#: indicative of the type; weak signals add supporting evidence. Both are
#: matched as lowercased word-boundary substrings so plurals and phrases are
#: handled without classifying on filenames.
_SIGNALS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    RESUME: (
        (
            "resume",
            "curriculum vitae",
            "work experience",
            "employment history",
            "professional summary",
            "objective",
        ),
        (
            "education",
            "skills",
            "references",
            "certifications",
            "accomplishments",
        ),
    ),
    INVOICE: (
        (
            "invoice",
            "invoice number",
            "amount due",
            "payment terms",
            "total due",
            "bill to",
        ),
        (
            "due date",
            "subtotal",
            "vat",
            "gst",
            "po number",
            "payment due",
            "net 30",
            "balance due",
        ),
    ),
    RECEIPT: (
        (
            "receipt",
            "total paid",
            "amount paid",
            "payment method",
            "transaction id",
        ),
        (
            "cashier",
            "thank you for your purchase",
            "change",
            "itemized",
            "gratuity",
            "store",
        ),
    ),
    PASSPORT: (
        (
            "passport",
            "passport number",
            "national id",
            "national identity",
            "identity card",
            "machine readable",
        ),
        (
            "place of birth",
            "country of issue",
            "date of birth",
            "nationality",
            "id number",
            "sex",
        ),
    ),
    FORM: (
        (
            "application form",
            "please complete",
            "official use only",
            "do not write in this space",
            "fill in",
        ),
        (
            "form",
            "section a",
            "section b",
            "signature",
            "questionnaire",
            "please provide",
            "date of birth",
        ),
    ),
}

#: Minimum winning score required before a type is reported.
_SCORE_THRESHOLD = 2

_STRONG_WEIGHT = 2
_WEAK_WEIGHT = 1


def _present(signal: str, text: str) -> bool:
    """Return whether a signal occurs in the lowercased text.

    Matching uses word boundaries and tolerates a trailing plural ``s`` so
    ``receipt``/``receipts`` and ``national id``/``national ids`` both match.

    Args:
        signal: The signal phrase to look for.
        text: The lowercased document text.

    Returns:
        True if the signal is present, otherwise False.
    """
    return re.search(rf"\b{re.escape(signal)}s?\b", text) is not None


class DocumentClassifier:
    """Classify extracted document text into a supported V1 type or ``unknown``.

    The approach is deterministic and dependency-free: every type has a set of
    strong and weak textual signals, the presence of each signal is scored
    (strong counts double), and the winning type must score at least
    ``_SCORE_THRESHOLD`` and strictly outscore every other type. Empty, short,
    or ambiguous text safely resolves to ``unknown``. Classification relies
    only on the text produced by the existing extraction/OCR pipeline, never on
    filenames.
    """

    def classify(self, text: str) -> str:
        """Classify extracted document text.

        Args:
            text: The cleaned extracted document text.

        Returns:
            One of the supported V1 type constants or ``UNKNOWN``.
        """
        if not text or not text.strip():
            return UNKNOWN
        lowered = text.lower()
        scores = {
            doc_type: self._score(lowered, strong, weak)
            for doc_type, (strong, weak) in _SIGNALS.items()
        }
        winner = max(scores, key=scores.get)
        if scores[winner] < _SCORE_THRESHOLD:
            return UNKNOWN
        for doc_type, score in scores.items():
            if doc_type != winner and score >= scores[winner]:
                return UNKNOWN
        return winner

    @staticmethod
    def _score(
        text: str,
        strong: tuple[str, ...],
        weak: tuple[str, ...],
    ) -> int:
        """Score a document against a type's strong and weak signals.

        Args:
            text: The lowercased document text.
            strong: The type's strong signal phrases.
            weak: The type's weak signal phrases.

        Returns:
            The weighted signal count.
        """
        score = 0
        for signal in strong:
            if _present(signal, text):
                score += _STRONG_WEIGHT
        for signal in weak:
            if _present(signal, text):
                score += _WEAK_WEIGHT
        return score