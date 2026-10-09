"""
Vector store service (Phase 5, spec section 16).

Wraps whichever concrete vector database NyayaAI uses (Chroma or FAISS)
behind one small interface:

    VectorStore
        ├── add(records)      -- upsert chunks + their embeddings
        ├── search(...)       -- top-K nearest neighbours, optional metadata filter
        ├── delete(chunk_ids)
        ├── update(records)   -- upsert semantics
        ├── filter(where)     -- metadata-only lookup
        ├── count()
        └── persist()

Rule 9/10:
- RAG components remain modular.
- Vector database providers remain replaceable.
- Nothing outside this module imports chromadb or faiss directly.

Supported backends:
    VECTOR_STORE_BACKEND=chroma
    VECTOR_STORE_BACKEND=faiss

The vector store uses one collection/index for all legal domains.
The domain is stored as metadata so retrieval can later use:

    where={"domain": "cyber"}

Storage layout:

    vector_store/
    ├── chroma/
    └── faiss/
        ├── index.faiss
        └── metadata.json
"""

from __future__ import annotations

import json
import sys
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict, field
from pathlib import Path



from app.config import get_settings


# ==========================================================================
# CONSTANTS
# ==========================================================================

# Chroma 0.5.5 reports:
#
#     maximum batch size 5461
#
# We deliberately stay below that limit.
#
# Example:
#
#     7681 records
#          ↓
#     5000 + 2681
#
# This prevents:
#
#     ValueError: Batch size 7681 exceeds maximum batch size 5461
#
CHROMA_BATCH_SIZE = 5000


# Metadata fields stored in Chroma / FAISS.
METADATA_FIELDS = (
    "domain",
    "document_type",
    "act_name",
    "section",
    "chapter",
    "jurisdiction",
    "language",
    "source",
    "year",
    "document_id",
)


# ==========================================================================
# DATA STRUCTURES
# ==========================================================================

@dataclass
class VectorRecord:
    """
    One embedded legal chunk ready to be added to the vector store.
    """

    chunk_id: str
    text: str
    embedding: list[float]
    domain: str

    document_type: str | None = None
    act_name: str | None = None
    section: str | None = None
    chapter: str | None = None
    jurisdiction: str | None = None
    language: str | None = None
    source: str | None = None
    year: int | None = None

    # Used for user-uploaded documents in Phase 12.
    document_id: str | None = None

    def metadata(self) -> dict:
        """
        Convert the record to flat metadata suitable for Chroma/FAISS.

        None values are removed because some vector databases reject
        metadata values of None.
        """

        raw = asdict(self)

        return {
            key: raw[key]
            for key in METADATA_FIELDS
            if raw.get(key) is not None
        }


@dataclass
class SearchResult:
    """
    One vector-search result.

    score:
        Higher means more similar.
    """

    chunk_id: str
    text: str
    score: float
    metadata: dict = field(default_factory=dict)


# ==========================================================================
# ABSTRACT VECTOR STORE INTERFACE
# ==========================================================================

class VectorStore(ABC):
    """
    Common interface implemented by Chroma and FAISS.
    """

    name: str = "base"

    @abstractmethod
    def add(self, records: list[VectorRecord]) -> int:
        """
        Upsert records.

        Returns:
            Number of records written.
        """
        ...

    @abstractmethod
    def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        where: dict | None = None,
    ) -> list[SearchResult]:
        """
        Search nearest neighbours.

        where:
            Optional exact metadata filter.

        Example:
            where={"domain": "cyber"}
        """
        ...

    @abstractmethod
    def delete(self, chunk_ids: list[str]) -> int:
        ...

    def update(self, records: list[VectorRecord]) -> int:
        """
        Default update implementation.

        Delete existing records and add the new records.
        """

        self.delete(
            [record.chunk_id for record in records]
        )

        return self.add(records)

    @abstractmethod
    def filter(
        self,
        where: dict,
        limit: int = 1000,
    ) -> list[dict]:
        """
        Metadata-only lookup.

        Returns:

            [
                {
                    "chunk_id": "...",
                    "metadata": {...}
                }
            ]
        """
        ...

    @abstractmethod
    def count(self) -> int:
        ...

    def persist(self) -> None:
        """
        Default persistence behaviour.

        Chroma persists automatically.

        FAISS overrides this because FAISS needs to explicitly write
        its index and metadata files.
        """

        return None


# ==========================================================================
# CHROMA BACKEND
# ==========================================================================

class ChromaVectorStore(VectorStore):
    """
    ChromaDB implementation.

    Chroma is the default backend because:

    1. It stores metadata natively.
    2. It supports metadata filtering.
    3. It provides persistent storage.
    4. It works naturally with domain-aware retrieval.

    Chroma has a maximum batch size, therefore add() and delete()
    process records in batches.
    """

    name = "chroma"

    COLLECTION_NAME = "legal_chunks"

    def __init__(self, persist_dir: str):

        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

        except ImportError as exc:
            raise RuntimeError(
                "chromadb is not installed. "
                "Run: pip install -r backend/requirements.txt"
            ) from exc

        Path(persist_dir).mkdir(
            parents=True,
            exist_ok=True,
        )

        # anonymized_telemetry=False: Chroma otherwise tries to POST a
        # telemetry event to PostHog on client start / collection
        # create / every query. On a machine without smooth outbound
        # connectivity that call can hang or error (this is the source
        # of the "Failed to send telemetry event ... capture() takes 1
        # positional argument but 3 were given" noise seen in the
        # server logs), adding avoidable latency and log spam to every
        # request. Disabling it removes both, and has no effect on
        # retrieval behaviour or accuracy.
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        self._collection = (
            self._client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={
                    "hnsw:space": "cosine"
                },
            )
        )

    # ------------------------------------------------------------------
    # ADD / UPSERT
    # ------------------------------------------------------------------

    def add(
        self,
        records: list[VectorRecord],
    ) -> int:

        if not records:
            return 0

        total_written = 0

        for start in range(
            0,
            len(records),
            CHROMA_BATCH_SIZE,
        ):

            batch = records[
                start:start + CHROMA_BATCH_SIZE
            ]

            self._collection.upsert(
                ids=[
                    record.chunk_id
                    for record in batch
                ],

                embeddings=[
                    record.embedding
                    for record in batch
                ],

                documents=[
                    record.text
                    for record in batch
                ],

                metadatas=[
                    record.metadata()
                    for record in batch
                ],
            )

            total_written += len(batch)

            print(
                f"  [chroma] upserted "
                f"{total_written}/{len(records)} records"
            )

        return total_written

    # ------------------------------------------------------------------
    # UPDATE
    # ------------------------------------------------------------------

    def update(
        self,
        records: list[VectorRecord],
    ) -> int:

        # Chroma's upsert already provides update semantics.
        return self.add(records)

    # ------------------------------------------------------------------
    # SEARCH
    # ------------------------------------------------------------------

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        where: dict | None = None,
    ) -> list[SearchResult]:

        if top_k <= 0:
            return []

        n = self.count()

        if n == 0:
            return []

        # Chroma normally respects n_results, but your Chroma 0.5.5
        # installation returned 6 records for n_results=5.
        #
        # Therefore we request top_k and ALSO enforce top_k ourselves
        # after receiving the response.
        requested_k = min(top_k, n)

        result = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=requested_k,
            where=where or None,
        )

        output: list[SearchResult] = []

        ids = result.get(
            "ids",
            [[]],
        )[0]

        documents = result.get(
            "documents",
            [[]],
        )[0]

        metadatas = result.get(
            "metadatas",
            [[]],
        )[0]

        distances = result.get(
            "distances",
            [[]],
        )[0]

        for (
            chunk_id,
            document,
            metadata,
            distance,
        ) in zip(
            ids,
            documents,
            metadatas,
            distances,
        ):

            # Chroma returns cosine distance:
            #
            # distance = 0
            #     means identical
            #
            # similarity = 1 - distance
            #
            # Higher similarity = better result.

            similarity = 1.0 - distance

            output.append(
                SearchResult(
                    chunk_id=chunk_id,
                    text=document,
                    score=similarity,
                    metadata=metadata or {},
                )
            )

        # Defensive top-K enforcement.
        return output[:top_k]

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    def delete(
        self,
        chunk_ids: list[str],
    ) -> int:

        if not chunk_ids:
            return 0

        total_deleted = 0

        for start in range(
            0,
            len(chunk_ids),
            CHROMA_BATCH_SIZE,
        ):

            batch = chunk_ids[
                start:start + CHROMA_BATCH_SIZE
            ]

            self._collection.delete(
                ids=batch
            )

            total_deleted += len(batch)

        return total_deleted

    # ------------------------------------------------------------------
    # FILTER
    # ------------------------------------------------------------------

    def filter(
        self,
        where: dict,
        limit: int = 1000,
    ) -> list[dict]:

        if limit <= 0:
            return []

        result = self._collection.get(
            where=where,
            limit=limit,
            include=["metadatas"],
        )

        ids = result.get(
            "ids",
            [],
        )

        metadatas = result.get(
            "metadatas",
            [],
        )

        return [
            {
                "chunk_id": chunk_id,
                "metadata": metadata or {},
            }
            for chunk_id, metadata
            in zip(ids, metadatas)
        ]

    # ------------------------------------------------------------------
    # COUNT
    # ------------------------------------------------------------------

    def count(self) -> int:
        return self._collection.count()


# ==========================================================================
# FAISS BACKEND
# ==========================================================================

class FAISSVectorStore(VectorStore):
    """
    FAISS implementation.

    FAISS itself does not store metadata, so metadata is maintained
    separately in metadata.json.

    Layout:

        vector_store/faiss/
            index.faiss
            metadata.json
    """

    name = "faiss"

    def __init__(
        self,
        persist_dir: str,
    ):

        try:
            import faiss  # noqa: F401

        except ImportError as exc:
            raise RuntimeError(
                "faiss-cpu is not installed. "
                "Run: pip install -r backend/requirements.txt"
            ) from exc

        self._faiss = __import__("faiss")

        self._dir = Path(
            persist_dir
        )

        self._dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._index_path = (
            self._dir / "index.faiss"
        )

        self._meta_path = (
            self._dir / "metadata.json"
        )

        self._lock = threading.Lock()

        self._dim: int | None = None

        self._index = None

        # chunk_id -> integer FAISS id
        self._id_map: dict[str, int] = {}

        # integer FAISS id -> record
        self._records: dict[str, dict] = {}

        self._next_id = 1

        self._load()

    # ------------------------------------------------------------------
    # LOAD
    # ------------------------------------------------------------------

    def _load(self) -> None:

        if self._meta_path.exists():

            with self._meta_path.open(
                encoding="utf-8"
            ) as file:

                saved = json.load(file)

            self._dim = saved.get(
                "dim"
            )

            self._id_map = saved.get(
                "id_map",
                {},
            )

            self._records = saved.get(
                "records",
                {},
            )

            self._next_id = saved.get(
                "next_id",
                1,
            )

        if (
            self._dim is not None
            and self._index_path.exists()
        ):

            self._index = (
                self._faiss.read_index(
                    str(self._index_path)
                )
            )

    # ------------------------------------------------------------------
    # PERSIST
    # ------------------------------------------------------------------

    def persist(self) -> None:

        if self._index is not None:

            self._faiss.write_index(
                self._index,
                str(self._index_path),
            )

        with self._meta_path.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                {
                    "dim": self._dim,
                    "id_map": self._id_map,
                    "records": self._records,
                    "next_id": self._next_id,
                },
                file,
            )

    # ------------------------------------------------------------------
    # ENSURE INDEX
    # ------------------------------------------------------------------

    def _ensure_index(
        self,
        dim: int,
    ) -> None:

        if self._index is not None:

            if self._dim != dim:

                raise ValueError(
                    f"Embedding dimension mismatch: "
                    f"index was built with dim={self._dim}, "
                    f"got dim={dim}. "
                    f"Re-embed with a consistent model "
                    f"or rebuild the index."
                )

            return

        self._dim = dim

        flat = self._faiss.IndexFlatIP(
            dim
        )

        self._index = (
            self._faiss.IndexIDMap2(
                flat
            )
        )

    # ------------------------------------------------------------------
    # ADD
    # ------------------------------------------------------------------

    def add(
        self,
        records: list[VectorRecord],
    ) -> int:

        if not records:
            return 0

        with self._lock:

            self._ensure_index(
                len(records[0].embedding)
            )

            existing = [
                self._id_map[
                    record.chunk_id
                ]
                for record in records
                if record.chunk_id
                in self._id_map
            ]

            if existing:

                self._index.remove_ids(
                    self._np_array(existing)
                )

            import numpy as np

            vectors = np.array(
                [
                    record.embedding
                    for record in records
                ],
                dtype="float32",
            )

            ids = []

            for record in records:

                int_id = self._id_map.get(
                    record.chunk_id,
                    self._next_id,
                )

                if (
                    record.chunk_id
                    not in self._id_map
                ):

                    self._id_map[
                        record.chunk_id
                    ] = int_id

                    self._next_id += 1

                ids.append(
                    int_id
                )

                self._records[
                    str(int_id)
                ] = {
                    "chunk_id": record.chunk_id,
                    "text": record.text,
                    "metadata": record.metadata(),
                }

            self._index.add_with_ids(
                vectors,
                np.array(
                    ids,
                    dtype="int64",
                ),
            )

        return len(records)

    # ------------------------------------------------------------------
    # UPDATE
    # ------------------------------------------------------------------

    def update(
        self,
        records: list[VectorRecord],
    ) -> int:

        return self.add(records)

    # ------------------------------------------------------------------
    # SEARCH
    # ------------------------------------------------------------------

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        where: dict | None = None,
    ) -> list[SearchResult]:

        if top_k <= 0:
            return []

        if (
            self._index is None
            or self._index.ntotal == 0
        ):
            return []

        import numpy as np

        query = np.array(
            [query_embedding],
            dtype="float32",
        )

        # When filtering metadata, over-fetch candidates because
        # FAISS itself does not understand metadata filters.

        fetch_k = (
            top_k * 5
            if where
            else top_k
        )

        fetch_k = min(
            fetch_k,
            self._index.ntotal,
        )

        scores, ids = (
            self._index.search(
                query,
                fetch_k,
            )
        )

        output: list[SearchResult] = []

        for score, int_id in zip(
            scores[0],
            ids[0],
        ):

            if int_id == -1:
                continue

            record = self._records.get(
                str(int_id)
            )

            if record is None:
                continue

            if (
                where
                and not self._matches(
                    record["metadata"],
                    where,
                )
            ):
                continue

            output.append(
                SearchResult(
                    chunk_id=record["chunk_id"],
                    text=record["text"],
                    score=float(score),
                    metadata=record["metadata"],
                )
            )

            if len(output) >= top_k:
                break

        return output[:top_k]

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    def delete(
        self,
        chunk_ids: list[str],
    ) -> int:

        if not chunk_ids:
            return 0

        with self._lock:

            int_ids = [
                self._id_map.pop(
                    chunk_id
                )
                for chunk_id in chunk_ids
                if chunk_id in self._id_map
            ]

            if not int_ids:
                return 0

            self._index.remove_ids(
                self._np_array(int_ids)
            )

            for int_id in int_ids:

                self._records.pop(
                    str(int_id),
                    None,
                )

        return len(int_ids)

    # ------------------------------------------------------------------
    # FILTER
    # ------------------------------------------------------------------

    def filter(
        self,
        where: dict,
        limit: int = 1000,
    ) -> list[dict]:

        if limit <= 0:
            return []

        output = []

        for (
            int_id,
            record,
        ) in self._records.items():

            if self._matches(
                record["metadata"],
                where,
            ):

                output.append(
                    {
                        "chunk_id": record["chunk_id"],
                        "metadata": record["metadata"],
                    }
                )

                if len(output) >= limit:
                    break

        return output

    # ------------------------------------------------------------------
    # COUNT
    # ------------------------------------------------------------------

    def count(self) -> int:

        if self._index is None:
            return 0

        return self._index.ntotal

    # ------------------------------------------------------------------
    # METADATA MATCH
    # ------------------------------------------------------------------

    @staticmethod
    def _matches(
        metadata: dict,
        where: dict,
    ) -> bool:

        return all(
            metadata.get(key) == value
            for key, value in where.items()
        )

    # ------------------------------------------------------------------
    # NUMPY ID ARRAY
    # ------------------------------------------------------------------

    def _np_array(
        self,
        ids: list[int],
    ):

        import numpy as np

        return np.array(
            ids,
            dtype="int64",
        )


# ==========================================================================
# VECTOR STORE FACTORY
# ==========================================================================

_store_lock = threading.Lock()

_store_instance: VectorStore | None = None


def get_vector_store() -> VectorStore:
    """
    Return the configured vector store.

    Configuration:

        VECTOR_STORE_BACKEND=chroma

    or:

        VECTOR_STORE_BACKEND=faiss

    The store is cached process-wide.
    """

    global _store_instance

    if _store_instance is not None:
        return _store_instance

    with _store_lock:

        if _store_instance is not None:
            return _store_instance

        settings = get_settings()

        backend = (
            settings.VECTOR_STORE_BACKEND
            .lower()
        )

        base_dir = Path(
            settings.VECTOR_STORE_DIR
        )

        if backend == "chroma":

            _store_instance = (
                ChromaVectorStore(
                    str(
                        base_dir / "chroma"
                    )
                )
            )

        elif backend == "faiss":

            _store_instance = (
                FAISSVectorStore(
                    str(
                        base_dir / "faiss"
                    )
                )
            )

        else:

            raise ValueError(
                f"Unknown VECTOR_STORE_BACKEND "
                f"'{settings.VECTOR_STORE_BACKEND}'. "
                f"Expected 'chroma' or 'faiss'."
            )

        return _store_instance


def reset_vector_store_cache() -> None:
    """
    Reset the cached vector-store instance.

    Mainly used by tests and by scripts that need to recreate the
    store after configuration changes.
    """

    global _store_instance

    with _store_lock:
        _store_instance = None