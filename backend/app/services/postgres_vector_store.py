"""PostgreSQL pgvector implementation for NyayaAI."""

import json
import os

import psycopg

from app.services.vector_store_service import (
    VectorStore,
    VectorRecord,
    SearchResult,
)


class PostgresVectorStore(VectorStore):
    name = "postgres"

    def __init__(self, database_url=None):
        self.database_url = database_url or os.environ.get("DATABASE_URL")
        if not self.database_url:
            raise ValueError("DATABASE_URL is required for PostgreSQL vectors")

    def _connect(self):
        return psycopg.connect(self.database_url, connect_timeout=30)

    @staticmethod
    def _vector(values):
        if len(values) != 768:
            raise ValueError("Expected 768-dimensional embedding")
        return "[" + ",".join(str(float(x)) for x in values) + "]"

    def add(self, records):
        if not records:
            return 0

        with self._connect() as conn:
            with conn.cursor() as cur:
                for record in records:
                    cur.execute(
                        """
                        INSERT INTO public.legal_vectors
                            (chunk_id, document_text, embedding, metadata)
                        VALUES (%s, %s, %s::extensions.vector, %s::jsonb)
                        ON CONFLICT (chunk_id) DO UPDATE SET
                            document_text = EXCLUDED.document_text,
                            embedding = EXCLUDED.embedding,
                            metadata = EXCLUDED.metadata
                        """,
                        (
                            record.chunk_id,
                            record.text,
                            self._vector(record.embedding),
                            json.dumps(record.metadata()),
                        ),
                    )
        return len(records)

    def search(self, query_embedding, top_k=10, where=None):
        if top_k <= 0:
            return []

        vector = self._vector(query_embedding)
        metadata_filter = json.dumps(where or {})

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    chunk_id,
                    document_text,
                    metadata,
                    1 - (embedding <=> %s::extensions.vector) AS score
                FROM public.legal_vectors
                WHERE metadata @> %s::jsonb
                ORDER BY embedding <=> %s::extensions.vector
                LIMIT %s
                """,
                (vector, metadata_filter, vector, top_k),
            ).fetchall()

        return [
            SearchResult(
                chunk_id=row[0],
                text=row[1],
                metadata=row[2],
                score=float(row[3]),
            )
            for row in rows
        ]

    def delete(self, chunk_ids):
        if not chunk_ids:
            return 0

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM public.legal_vectors
                    WHERE chunk_id = ANY(%s)
                    """,
                    (chunk_ids,),
                )
                return cur.rowcount

    def update(self, records):
        return self.add(records)

    def filter(self, where, limit=1000):
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT chunk_id, metadata
                FROM public.legal_vectors
                WHERE metadata @> %s::jsonb
                ORDER BY chunk_id
                LIMIT %s
                """,
                (json.dumps(where), limit),
            ).fetchall()

        return [
            {"chunk_id": row[0], "metadata": row[1]}
            for row in rows
        ]

    def count(self):
        with self._connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM public.legal_vectors"
            ).fetchone()[0]

    def persist(self):
        # PostgreSQL transactions commit automatically on context exit.
        return None
