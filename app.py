import ollama

from rag_engine import CodebaseRAG


LLM_MODEL = "llama3.2:1b"


def generate_answer(question, retrieved_chunks):
    if not retrieved_chunks:
        return (
            "I couldn't find relevant information in the indexed codebase. "
            "Try asking a more specific question."
        )

    context_parts = []

    for chunk, metadata in retrieved_chunks:
        file_path = metadata.get("file_path", "Unknown file")
        start_line = metadata.get("start_line", "?")
        end_line = metadata.get("end_line", "?")

        context_parts.append(
            f"""
File: {file_path}
Lines: {start_line}-{end_line}

Code:
{chunk}
"""
        )

    context = "\n\n".join(context_parts)

    system_prompt = """
You are a careful AI software engineer analyzing a codebase.

Your task is to answer questions using ONLY the supplied source code.

STRICT RULES:

1. Never invent functions, variables, files, APIs, database tables,
   libraries, features, or implementation details.

2. Treat the supplied source code as evidence, not assumptions.

3. If the answer is not supported by the supplied code, explicitly say:
   "I couldn't verify this from the retrieved source code."

4. Distinguish between implemented functionality and functionality
   that is merely suggested by a function name or comment.

5. When explaining execution flow, follow only the calls and behavior
   visible in the supplied code. Clearly identify missing information.

6. If only part of the answer is supported, explain the verified part
   and identify what remains uncertain.

7. Cite the relevant file paths and line numbers when available.

8. Be concise, precise, and honest about uncertainty.

9. Do not assume that a function works in a particular way merely
   because of its name.

10. If the context is insufficient, do not guess.
"""

    user_prompt = f"""
QUESTION:
{question}

RETRIEVED SOURCE CODE:
{context}

Answer the question using the source code and the rules above.
"""

    response = ollama.chat(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        options={
            "temperature": 0,
            "num_ctx": 4096,
        },
    )

    return response["message"]["content"]


def main():

    rag = CodebaseRAG()

    rag.index_codebase()

    while True:

        question = input(
            "\nAsk about the codebase "
            "(or type 'exit'): "
        ).strip()

        if question.lower() == "exit":
            break

        if not question:
            continue

        retrieved_chunks = rag.retrieve(
            question,
            top_k=3,
        )

        if not retrieved_chunks:

            print("No relevant code was found.")

            continue

        print("\nRetrieved source code:")

        for chunk in retrieved_chunks:

            print(
                f"- {chunk['file_path']}:"
                f"{chunk['start_line']}-"
                f"{chunk['end_line']} "
                f"(distance: {chunk['distance']:.3f})"
            )

        answer = generate_answer(
            question,
            retrieved_chunks,
        )

        print("\nAI Assistant:")
        print(answer)


if __name__ == "__main__":
    main()