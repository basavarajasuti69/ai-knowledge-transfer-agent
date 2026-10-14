from pathlib import Path

import chromadb
import ast
from sentence_transformers import SentenceTransformer


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_PATH = Path("sample_project")
DATABASE_PATH = Path("chroma_db")

EMBEDDING_MODEL = "all-MiniLM-L6-v2"

COLLECTION_NAME = "codebase_chunks"
TEMP_COLLECTION_NAME = "codebase_chunks_build"

SUPPORTED_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".java",
    ".html",
    ".css",
    ".json",
}

IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "chroma_db",
    ".next",
    "dist",
    "build",
}

CHUNK_SIZE = 30
CHUNK_OVERLAP = 5
BATCH_SIZE = 100

# Experimental starting value, not a universal cutoff.
MIN_SIMILARITY = 0.30


# ============================================================
# RAG ENGINE
# ============================================================

class CodebaseRAG:

    def __init__(self):

        print("Loading embedding model...")

        self.embedding_model = SentenceTransformer(
            EMBEDDING_MODEL
        )

        print("Connecting to ChromaDB...")

        self.chroma_client = chromadb.PersistentClient(
            path=str(DATABASE_PATH)
        )

        # Create or connect to the collection.
        # Cosine distance is used for vector comparison.
        self.collection = (
            self.chroma_client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={
                    "description": "Source code embeddings",
                    "hnsw:space": "cosine",
                },
            )
        )

        print("RAG engine initialized successfully.")

    # ========================================================
    # READ SOURCE FILES
    # ========================================================

    def read_files(self):

        if not PROJECT_PATH.exists():

            raise FileNotFoundError(
                f"Project folder not found: {PROJECT_PATH.resolve()}"
            )

        files = []

        for path in PROJECT_PATH.rglob("*"):

            if not path.is_file():
                continue

            # Ignore generated and irrelevant directories.
            if any(
                part in IGNORED_DIRECTORIES
                for part in path.parts
            ):
                continue

            # Read only supported source files.
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            try:

                content = path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )

                if not content.strip():
                    continue

                relative_path = path.relative_to(
                    PROJECT_PATH
                )

                files.append({
                    "path": relative_path.as_posix(),
                    "content": content,
                })

            except OSError as error:

                print(
                    f"Could not read {path}: {error}"
                )

        return files

    # ========================================================
    # SPLIT SOURCE CODE INTO CHUNKS
    # ========================================================

    def chunk_code(
        self,
        content,
        chunk_size=CHUNK_SIZE,
        overlap=CHUNK_OVERLAP,
    ):
        """Split source into function/class-aware chunks where possible."""
        lines = content.splitlines()

        if not lines:
            return []

        def line_based_chunks():
            chunks = []
            start = 0

            while start < len(lines):
                end = min(start + chunk_size, len(lines))
                text = "\n".join(lines[start:end])

                if text.strip():
                    chunks.append({
                        "text": text,
                        "start_line": start + 1,
                        "end_line": end,
                    })

                if end == len(lines):
                    break

                start = end - overlap

            return chunks

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return line_based_chunks()

        blocks = []
        for node in tree.body:
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            ):
                start_line = node.lineno
                if getattr(node, "decorator_list", None):
                    start_line = min(
                        decorator.lineno for decorator in node.decorator_list
                    )

                blocks.append({
                    "start_line": start_line,
                    "end_line": node.end_lineno,
                })

        if not blocks:
            return line_based_chunks()

        chunks = []
        cursor = 1

        def add_line_chunks(start_line, end_line):
            if start_line > end_line:
                return

            current = start_line
            while current <= end_line:
                end = min(current + chunk_size - 1, end_line)
                text = "\n".join(lines[current - 1:end])

                if text.strip():
                    chunks.append({
                        "text": text,
                        "start_line": current,
                        "end_line": end,
                    })

                if end == end_line:
                    break

                current = end - overlap + 1

        def add_block(start_line, end_line):
            block_size = end_line - start_line + 1
            if block_size <= chunk_size:
                text = "\n".join(lines[start_line - 1:end_line])
                if text.strip():
                    chunks.append({
                        "text": text,
                        "start_line": start_line,
                        "end_line": end_line,
                    })
            else:
                add_line_chunks(start_line, end_line)

        for block in blocks:
            start_line = block["start_line"]
            end_line = block["end_line"]

            if cursor < start_line:
                add_line_chunks(cursor, start_line - 1)

            add_block(start_line, end_line)
            cursor = max(cursor, end_line + 1)

        if cursor <= len(lines):
            add_line_chunks(cursor, len(lines))

        return chunks

    # ========================================================
    # INDEX THE REPOSITORY
    # ========================================================

    def index_codebase(self):

        print("\nReading source files...")

        files = self.read_files()

        if not files:

            raise ValueError(
                "No supported source files found in "
                f"{PROJECT_PATH.resolve()}"
            )

        documents = []
        metadatas = []
        ids = []

        # Create chunks for every source file.
        for file in files:

            chunks = self.chunk_code(
                file["content"]
            )

            for index, chunk in enumerate(chunks):

                documents.append(
                    chunk["text"]
                )

                metadatas.append({
                    "file_path": file["path"],
                    "start_line": chunk["start_line"],
                    "end_line": chunk["end_line"],
                })

                ids.append(
                    f"{file['path']}::chunk_{index}"
                )

        if not documents:

            raise ValueError(
                "No code chunks were generated."
            )

        print(
            f"Found {len(files)} files and "
            f"{len(documents)} code chunks."
        )

        # Generate vector embeddings.
        print("Generating embeddings...")

        embeddings = self.embedding_model.encode(
            documents,
            normalize_embeddings=True,
            show_progress_bar=True,
        ).tolist()

        # ----------------------------------------------------
        # BUILD A TEMPORARY COLLECTION
        # ----------------------------------------------------

        try:
            self.chroma_client.delete_collection(
                name=TEMP_COLLECTION_NAME
            )
        except Exception:
            pass

        temp_collection = (
            self.chroma_client.create_collection(
                name=TEMP_COLLECTION_NAME,
                metadata={
                    "description": "Temporary source code index",
                    "hnsw:space": "cosine",
                },
            )
        )

        for start in range(0, len(documents), BATCH_SIZE):
            end = min(start + BATCH_SIZE, len(documents))

            temp_collection.add(
                ids=ids[start:end],
                documents=documents[start:end],
                metadatas=metadatas[start:end],
                embeddings=embeddings[start:end],
            )

        if temp_collection.count() != len(documents):
            raise RuntimeError(
                "Temporary index validation failed."
            )

        # ----------------------------------------------------
        # REPLACE THE MAIN COLLECTION
        # ----------------------------------------------------

        try:
            self.chroma_client.delete_collection(
                name=COLLECTION_NAME
            )
        except Exception:
            pass

        self.collection = (
            self.chroma_client.create_collection(
                name=COLLECTION_NAME,
                metadata={
                    "description": "Source code embeddings",
                    "hnsw:space": "cosine",
                },
            )
        )

        for start in range(0, len(documents), BATCH_SIZE):
            end = min(start + BATCH_SIZE, len(documents))

            self.collection.add(
                ids=ids[start:end],
                documents=documents[start:end],
                metadatas=metadatas[start:end],
                embeddings=embeddings[start:end],
            )

        self.chroma_client.delete_collection(
            name=TEMP_COLLECTION_NAME
        )

        print(
            f"\nSuccessfully indexed "
            f"{self.collection.count()} code chunks."
        )

    # ========================================================
    # RETRIEVE RELEVANT SOURCE CODE
    # ========================================================

    def retrieve(
        self,
        question,
        top_k=5,
        min_similarity=MIN_SIMILARITY,
    ):

        if not question or not question.strip():
            return []

        if top_k < 1:
            raise ValueError(
                "top_k must be at least 1."
            )

        if not 0 <= min_similarity <= 1:
            raise ValueError(
                "min_similarity must be between 0 and 1."
            )

        total_chunks = self.collection.count()

        if total_chunks == 0:

            print(
                "No code is indexed. "
                "Run index_codebase() first."
            )

            return []

        # Embed the user's question.
        question_embedding = (
            self.embedding_model.encode(
                question,
                normalize_embeddings=True,
            ).tolist()
        )

        # Retrieve the nearest source-code chunks.
        results = self.collection.query(
            query_embeddings=[
                question_embedding
            ],
            n_results=min(
                top_k,
                total_chunks,
            ),
            include=[
                "documents",
                "metadatas",
                "distances",
            ],
        )

        retrieved_chunks = []

        result_documents = results["documents"][0] or []
        result_metadatas = results["metadatas"][0] or []
        result_distances = results["distances"][0] or []

        for document, metadata, distance in zip(
            result_documents,
            result_metadatas,
            result_distances,
        ):

            # ChromaDB returns cosine distance when the collection
            # uses hnsw:space = cosine.
            similarity = 1.0 - distance

            print(
                f"{metadata['file_path']} "
                f"(lines {metadata['start_line']}-"
                f"{metadata['end_line']}): "
                f"similarity={similarity:.3f}"
            )

            # Exclude chunks below the experimental threshold.
            if similarity < min_similarity:
                continue

            retrieved_chunks.append({
                "text": document,
                "file_path": metadata["file_path"],
                "start_line": metadata["start_line"],
                "end_line": metadata["end_line"],
                "distance": distance,
                "similarity": similarity,
            })

        if not retrieved_chunks:

            print(
                "No chunks passed the similarity threshold."
            )

        return retrieved_chunks
