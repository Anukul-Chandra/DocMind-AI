"""PDF text extraction for the document indexing pipeline."""

import fitz


class PDFProcessor:
    """Extract clean text content from a PDF file on disk.

    PDFs with a selectable text layer are extracted directly. Image-only
    (scanned) PDFs fall back to OCR: each page is rasterized and recognized
    through the Tesseract engine that PyMuPDF integrates with, and the
    recognized text is returned through the same extraction result so the
    downstream pipeline (cleaning, chunking, embedding, indexing) is unchanged.
    """

    def __init__(self, ocr_language: str = "eng", ocr_dpi: int = 150) -> None:
        """Initialize the processor with OCR settings used as a fallback.

        Args:
            ocr_language: The Tesseract language code used for OCR.
            ocr_dpi: The rasterization resolution used for OCR pages.
        """
        self._ocr_language = ocr_language
        self._ocr_dpi = ocr_dpi

    def extract_text(self, file_path: str) -> str:
        """Extract the text from every page of the PDF, OCR'ing if needed.

        Selectable text is concatenated across pages. If that yields no usable
        text, the pages are rendered and recognized with OCR instead.

        Args:
            file_path: Filesystem path to the PDF file.

        Returns:
            The concatenated page text, stripped of leading/trailing whitespace.

        Raises:
            ValueError: If the file is not a readable PDF, the OCR engine is
                unavailable, or no text could be extracted.
        """
        try:
            doc = fitz.open(file_path)
        except Exception as exc:
            raise ValueError(f"Invalid or corrupted PDF file: {file_path}") from exc
        try:
            text = self._extract_selectable_text(doc)
            if not text:
                text = self._extract_text_with_ocr(doc)
        finally:
            doc.close()
        text = text.strip()
        if not text:
            raise ValueError(f"The PDF contains no extractable text: {file_path}")
        return text

    def _extract_selectable_text(self, doc: fitz.Document) -> str:
        """Concatenate the selectable text layer of every page.

        Args:
            doc: The opened PDF document.

        Returns:
            The concatenated page text.
        """
        return "\n".join(page.get_text() for page in doc)

    def _extract_text_with_ocr(self, doc: fitz.Document) -> str:
        """Recognize the text of an image-only PDF page by page.

        Each page is rasterized at ``self._ocr_dpi`` and recognized with the
        Tesseract engine that PyMuPDF integrates with.

        Args:
            doc: The opened PDF document.

        Returns:
            The concatenated OCR text for every page.

        Raises:
            ValueError: If the OCR engine is unavailable or fails on a page.
        """
        pages = []
        for page in doc:
            try:
                textpage = page.get_textpage_ocr(
                    language=self._ocr_language,
                    dpi=self._ocr_dpi,
                    full=True,
                )
            except Exception as exc:
                raise ValueError(
                    f"OCR failed while extracting an image-only page: {exc}"
                ) from exc
            pages.append(page.get_text(textpage=textpage))
        return "\n".join(pages)
