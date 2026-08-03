"""PDF text extraction for the document indexing pipeline."""

import fitz


class PDFProcessor:
    """Extract clean text content from a PDF file on disk."""

    def extract_text(self, file_path: str) -> str:
        """Extract the text from every page of the PDF.

        Args:
            file_path: Filesystem path to the PDF file.

        Returns:
            The concatenated page text, stripped of leading/trailing whitespace.

        Raises:
            ValueError: If the file is not a readable PDF or contains no
                extractable text.
        """
        try:
            doc = fitz.open(file_path)
        except Exception as exc:
            raise ValueError(f"Invalid or corrupted PDF file: {file_path}") from exc
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        text = text.strip()
        if not text:
            raise ValueError(f"The PDF contains no extractable text: {file_path}")
        return text
