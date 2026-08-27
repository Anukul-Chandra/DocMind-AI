"""Read-only consistency checker for the document storage stores.

The application persists documents across four independent stores:

- physical PDF files under the configured storage directory,
- the FAISS vector index (VectorStore / index.faiss),
- chunk metadata (MetadataStore / metadata.json),
- the document registry (documents.json or the PostgreSQL documents table,
  both behind the DocumentRepository interface).

The FAISS-to-metadata relationship is positional: FAISS index ``i``
corresponds to the metadata record stored at index ``i`` (whose ``id`` field
is ``i + 1``). This checker reports whether that relationship and the
metadata-to-registry linkage still hold. It is strictly detection: it never
deletes files, rewrites metadata, rewrites the FAISS index, mutates the
document registry, or changes ownership or deletion flags.

A report is ``healthy`` only when there are no actual inconsistencies. Legacy
ownerless chunks (``document_id == ""``) and chunks of soft-deleted documents
are reported but do not affect health, because both are documented,
by-design states of the current system.
"""

from dataclasses import dataclass, field
from pathlib import Path

from app.repositories.interfaces import DocumentRepository
from app.services.storage_backends import MetadataBackend, VectorBackend

PHYSICAL_FILE_PATTERNS = ("*.pdf",)


@dataclass(frozen=True)
class ChunkReference:
    """A single metadata chunk with the linkage information available.

    Attributes:
        metadata_id: The chunk's id as stored in the metadata record.
        document_id: The owning document id from the metadata record.
        workspace_id: The workspace recorded on the chunk.
        owner_id: The owner recorded on the chunk.
        filename: The display filename recorded on the chunk.
    """

    metadata_id: int
    document_id: str
    workspace_id: str
    owner_id: str
    filename: str


@dataclass(frozen=True)
class ChunkCountMismatch:
    """A registry record whose declared chunk count differs from its chunks.

    Attributes:
        document_id: The registered document id.
        owner_id: The owner of the registered document.
        workspace_id: The workspace of the registered document.
        registry_chunk_count: The ``chunk_count`` stored in the registry.
        metadata_chunk_count: The number of metadata chunks referencing it.
    """

    document_id: str
    owner_id: str
    workspace_id: str
    registry_chunk_count: int
    metadata_chunk_count: int


@dataclass(frozen=True)
class ConsistencyReport:
    """Result of a consistency check across the document storage stores.

    Attributes:
        vector_count: Number of vectors in the FAISS index.
        metadata_count: Number of records in the metadata store.
        vector_metadata_match: Whether both counts are equal.
        unmatched_vector_indices: FAISS positions with no metadata record
            (metadata is shorter than FAISS).
        metadata_without_vector_ids: Metadata ids with no FAISS vector
            (metadata is longer than FAISS).
        orphan_metadata: Chunks referencing a document unknown to the registry.
        legacy_ownerless_chunks: Chunks with an empty document id.
        deleted_document_chunks: Chunks of registered, soft-deleted documents.
        registry_chunk_count_mismatches: Registry records whose ``chunk_count``
            does not match the number of metadata chunks referencing them.
        missing_physical_files: Physical files the registry implies but that
            are absent. Empty when the registry does not preserve enough
            information to map them.
        orphan_physical_files: Physical files with no registry record. Empty
            when the mapping is unavailable.
        physical_file_mapping_available: Whether physical files could be
            reliably attributed to registry records.
        notes: Human-readable observations and limitations.
    """

    vector_count: int
    metadata_count: int
    vector_metadata_match: bool
    unmatched_vector_indices: list[int] = field(default_factory=list)
    metadata_without_vector_ids: list[int] = field(default_factory=list)
    orphan_metadata: list[ChunkReference] = field(default_factory=list)
    legacy_ownerless_chunks: list[ChunkReference] = field(default_factory=list)
    deleted_document_chunks: list[ChunkReference] = field(default_factory=list)
    registry_chunk_count_mismatches: list[ChunkCountMismatch] = field(
        default_factory=list
    )
    missing_physical_files: list[str] = field(default_factory=list)
    orphan_physical_files: list[str] = field(default_factory=list)
    physical_file_mapping_available: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        """Return whether no actual inconsistency was detected.

        Legacy ownerless chunks and chunks of soft-deleted documents are
        documented, by-design states and do not make the report unhealthy.

        Returns:
            True when the vector/metadata counts match, no vector lacks
            metadata, no metadata lacks a vector, no chunk references an
            unknown document, and every registry chunk count matches.
        """
        return (
            self.vector_metadata_match
            and not self.unmatched_vector_indices
            and not self.metadata_without_vector_ids
            and not self.orphan_metadata
            and not self.registry_chunk_count_mismatches
        )


def _chunk_reference(metadata_id: int, record: dict) -> ChunkReference:
    """Build a ChunkReference from a metadata record.

    Args:
        metadata_id: The chunk's id as stored in the metadata record.
        record: The metadata record.

    Returns:
        A ChunkReference capturing the available linkage information.
    """
    return ChunkReference(
        metadata_id=metadata_id,
        document_id=record.get("document_id", "") or "",
        workspace_id=record.get("workspace_id", "") or "",
        owner_id=record.get("owner_id", "") or "",
        filename=record.get("filename", "") or "",
    )


def _check_physical_files(
    report: ConsistencyReport,
    storage_dir: str | Path | None,
) -> None:
    """Populate the physical-file findings of a report in place.

    The registry records only the original client filename (e.g. ``report.pdf``)
    while uploads are stored under server-generated names
    (``storage/<hex>.<ext>``), so registry documents cannot be reliably mapped
    to physical files. The limitation is reported explicitly instead of
    guessing, and candidate files are counted only as an observation.

    Args:
        report: The report to populate.
        storage_dir: Optional path to the storage directory to inspect.
    """
    if storage_dir is None:
        return
    report.notes.append(
        "Registry records store the original client filename only (e.g. "
        "'report.pdf'), not the server-generated storage filename; physical "
        "uploads live under storage/<hex>.<ext>. Documents cannot be reliably "
        "mapped to physical files, so missing/orphan file lists are left "
        "empty rather than guessed."
    )
    candidates: list[Path] = []
    for pattern in PHYSICAL_FILE_PATTERNS:
        candidates.extend(Path(storage_dir).glob(pattern))
    candidates = sorted({path for path in candidates})
    if candidates:
        report.notes.append(
            f"storage_dir contains {len(candidates)} physical file(s) that "
            "cannot be attributed to registry records."
        )


def check_consistency(
    vector_store: VectorBackend,
    metadata_store: MetadataBackend,
    document_repository: DocumentRepository,
    storage_dir: str | Path | None = None,
) -> ConsistencyReport:
    """Audit the consistency of the document storage stores, read-only.

    Args:
        vector_store: The FAISS-backed vector store to audit.
        metadata_store: The chunk metadata store to audit.
        document_repository: The document registry behind the repository
            interface (JSON or PostgreSQL backed).
        storage_dir: Optional path to the storage directory for the
            physical-file observation.

    Returns:
        A ConsistencyReport describing every detected divergence.
    """
    records = metadata_store.get_all_documents()
    vector_count = vector_store.ntotal
    metadata_count = len(records)

    unmatched_vector_indices = []
    if vector_count > metadata_count:
        unmatched_vector_indices = list(range(metadata_count, vector_count))

    metadata_without_vector_ids = []
    if metadata_count > vector_count:
        metadata_without_vector_ids = [
            record.get("id") for record in records[vector_count:]
        ]

    sequential_ids = [record.get("id") for record in records]
    if sequential_ids != list(range(1, metadata_count + 1)):
        report = ConsistencyReport(
            vector_count=vector_count,
            metadata_count=metadata_count,
            vector_metadata_match=vector_count == metadata_count,
            unmatched_vector_indices=unmatched_vector_indices,
            metadata_without_vector_ids=metadata_without_vector_ids,
            notes=[
                "Metadata record ids are not sequential 1..N; the positional "
                "FAISS-to-metadata correspondence cannot be trusted."
            ],
        )
        _check_physical_files(report, storage_dir)
        return report

    registry = document_repository.list_all_documents()
    registry_by_id = {document.document_id: document for document in registry}

    orphan_metadata: list[ChunkReference] = []
    legacy_ownerless_chunks: list[ChunkReference] = []
    deleted_document_chunks: list[ChunkReference] = []
    chunks_by_document: dict[str, int] = {}

    for position, record in enumerate(records):
        reference = _chunk_reference(record.get("id"), record)
        document_id = reference.document_id
        if not document_id:
            legacy_ownerless_chunks.append(reference)
            continue
        registered = registry_by_id.get(document_id)
        if registered is None:
            orphan_metadata.append(reference)
            continue
        chunks_by_document[document_id] = chunks_by_document.get(document_id, 0) + 1
        if registered.deleted:
            deleted_document_chunks.append(reference)

    registry_chunk_count_mismatches = []
    for document in registry:
        actual = chunks_by_document.get(document.document_id, 0)
        if document.chunk_count != actual:
            registry_chunk_count_mismatches.append(
                ChunkCountMismatch(
                    document_id=document.document_id,
                    owner_id=document.owner_id,
                    workspace_id=document.workspace_id,
                    registry_chunk_count=document.chunk_count,
                    metadata_chunk_count=actual,
                )
            )

    report = ConsistencyReport(
        vector_count=vector_count,
        metadata_count=metadata_count,
        vector_metadata_match=vector_count == metadata_count,
        unmatched_vector_indices=unmatched_vector_indices,
        metadata_without_vector_ids=metadata_without_vector_ids,
        orphan_metadata=orphan_metadata,
        legacy_ownerless_chunks=legacy_ownerless_chunks,
        deleted_document_chunks=deleted_document_chunks,
        registry_chunk_count_mismatches=registry_chunk_count_mismatches,
    )
    _check_physical_files(report, storage_dir)
    return report
