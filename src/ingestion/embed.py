from pathlib import Path
import json
from src.core.logging import get_logger
from .constants import CHUNKS_DIR
from src.core.db import get_session
from sqlalchemy import delete, insert
from src.models.chunk import Chunk
from tqdm import tqdm

from src.core.embedding import embed_texts

from src.policypal.config import settings

CHUNKS_PATH = CHUNKS_DIR / "all_chunks.jsonl"
BATCH_SIZE = 64

logger = get_logger(__name__)

def _load_chunks(file_path: Path) -> list[dict]:
    if file_path is None or not file_path.exists(): 
        raise FileNotFoundError(f"{file_path} path doesn't exist, provide a valid file path. \
                                First run chunk stage first.")

    chunks: list[dict] = []

    with open(file_path, "r+", encoding="utf-8") as file:
        for line_no, chunk in enumerate(file.readlines(), start=1):
            chunk = chunk.strip()

            if not chunk: continue

            try:
                chunks.append(json.loads(chunk))
            except json.JSONDecodeError:
                logger.warning("skipping JSON at line %d", line_no)
    
    return chunks


def execute(chunks_path: Path=CHUNKS_PATH, batch_size: int=BATCH_SIZE, rebuild: bool = True) -> None:
    chunks = _load_chunks(chunks_path)

    if not chunks:
        logger.warning("no chunks to embed. aborting.")
        return
    
    logger.info("loaded %d chunks from %s", len(chunks), chunks_path)

    with get_session() as session:
        if rebuild:
            deleted = session.execute(delete(Chunk)).rowcount
            logger.info("rebuild=True — cleared %d existing rows", deleted or 0)

        total = 0

        for start in tqdm(range(0, len(chunks), batch_size), desc="Embedding"):
            curr_chunks = chunks[start: start + batch_size]

            texts = [chunk["text"] for chunk in curr_chunks]

            embedded_vectors = embed_texts(texts)

            if embedded_vectors and len(embedded_vectors[0]) != settings.embedding_dim:
                raise ValueError(
                    f"Embedding dim mismatch: model returned {len(embedded_vectors[0])}, "
                    f"but settings.embedding_dim is {settings.embedding_dim}. "
                    "Update embedding_dim, the model, and the Vector(dim) migration "
                    "to all match."
                )
            
            session.execute(
                insert(Chunk),
                [
                    {
                        "content": chunk["text"],
                        "source": chunk["metadata"]["source_file"],
                        "embedding": em_vector
                    }
                    for chunk, em_vector in zip(curr_chunks, embedded_vectors)
                ],
            )

            total += len(curr_chunks)

        logger.info("Embedded and stored %d chunks", total)

            
if __name__ == "__main__":
    from src.core.logging import setup_logging
    setup_logging()
    execute()