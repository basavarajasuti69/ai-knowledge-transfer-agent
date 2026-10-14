import os

import streamlit as st
import ollama

from rag_engine import CodebaseRAG
from code_analyzer import CodeAnalyzer

# ---------------------------------
# Configuration
# ---------------------------------

LLM_MODEL = os.getenv("LLM_MODEL", "llama3.2:1b")

TOP_K = 5
MIN_SIMILARITY = 0.30


# ---------------------------------
# Page configuration
# ---------------------------------

st.set_page_config(
    page_title="AI Knowledge Transfer Agent",
    page_icon="🤖",
    layout="wide",
)


# ---------------------------------
# Load RAG engine
# ---------------------------------

@st.cache_resource
def load_rag_engine():

    rag = CodebaseRAG()

    if rag.collection.count() == 0:
        rag.index_codebase()

    return rag

@st.cache_resource
def load_code_analyzer():
    return CodeAnalyzer(project_path="sample_project")


def answer_execution_flow_question(question, analyzer):
    question_lower = question.lower()

    flow_phrases = [
        "how does this application work",
        "how does the application work",
        "explain the execution flow",
        "explain application flow",
        "what happens when the application starts",
        "how does the code execute",
    ]

    if any(phrase in question_lower for phrase in flow_phrases):
        return analyzer.explain_execution_flow()

    return None


def answer_caller_analysis_question(question, analyzer):
    question_lower = question.lower()

    supported_phrases = [
        "who calls",
        "callers of",
        "is the return value of",
        "return value checked",
        "return value handled",
        "could get_user returning none",
        "what happens if a function returns none",
    ]

    if not any(
        phrase in question_lower for phrase in supported_phrases
    ):
        return None

    function_name = None

    if "get_user" in question_lower:
        function_name = "get_user"
    elif "connect_database" in question_lower:
        function_name = "connect_database"

    if function_name is None:
        return (
            "Please specify a supported function, such as "
            "`get_user` or `connect_database`."
        )

    results = analyzer.analyze_function_callers(function_name)

    if not results:
        return f"No callers of `{function_name}()` were found."

    lines = [
        f"## Caller Analysis: `{function_name}()`",
        "",
    ]

    for result in results:
        lines.append(
            f"- **File:** `{result['file']}`\n"
            f"  - **Caller:** `{result['caller']}()`\n"
            f"  - **Line:** {result['line']}\n"
            f"  - **Assigned variable:** "
            f"`{result['assigned_variable']}`\n"
            f"  - **Truthiness check detected:** "
            f"{result['truthiness_check_found']}"
        )

    lines.extend([
        "",
        "**Limitation:** A detected truthiness check does not prove "
        "that every use of the result is safe.",
    ])

    return "\n".join(lines)


def answer_dependency_question(question, analyzer):
    question_lower = question.lower()

    dependency_phrases = [
        "project dependencies",
        "analyze dependencies",
        "which files does",
        "what does main.py depend on",
        "what files depend on",
        "which modules are imported",
        "explain the project dependencies",
    ]

    if not any(
        phrase in question_lower
        for phrase in dependency_phrases
    ):
        return None

    dependencies = analyzer.analyze_dependencies()

    if not dependencies:
        return "No Python import statements were found."

    lines = ["## Project Dependency Analysis", ""]

    for dependency in dependencies:
        file_name = dependency["file"]
        module = dependency["module"]
        imported_names = dependency["imported_names"]
        line_number = dependency["line"]

        if imported_names:
            imported_text = ", ".join(imported_names)
            description = f"`{imported_text}` from `{module}`"
        else:
            description = f"module `{module}`"

        lines.append(
            f"- **`{file_name}`**, line {line_number}: "
            f"imports {description}"
        )

    lines.extend([
        "",
        "**Note:** These results show detected import statements. "
        "They do not establish every runtime dependency or guarantee "
        "that every imported module is a local project file.",
    ])

    return "\n".join(lines)


def answer_test_failure_explanation_question(question, analyzer):
    """Explain test failures only when an actual test failure exists."""

    question_lower = question.lower()

    failure_phrases = [
        "explain test failure",
        "explain test failures",
        "why did my test fail",
        "why is my test failing",
        "analyze test failure",
        "analyze test failures",
    ]

    if not any(
        phrase in question_lower
        for phrase in failure_phrases
    ):
        return None

    supported_functions = ["get_user", "connect_database"]

    function_name = next(
        (
            name
            for name in supported_functions
            if name in question_lower
        ),
        None,
    )

    if not function_name:
        return (
            "Please specify a supported function: "
            "`get_user()` or `connect_database()`."
        )

    with st.spinner(f"Running tests for {function_name}..."):
        result = analyzer.run_tests(function_name)

    if result.get("success"):
        return (
            f"## Test Results: `{function_name}()`\n\n"
            "✅ All tests passed.\n\n"
            "There is no observed test failure to explain. "
            "No failure has been established by this test run."
        )

    output = result.get(
        "combined_output",
        result.get("output", "") + "\n" + result.get("errors", ""),
    )

    if not output.strip():
        return (
            f"Test execution for `{function_name}()` did not succeed, "
            "but no diagnostic output was captured. "
            "Check the test environment and execution errors."
        )

    with st.spinner("Explaining the captured test failure..."):
        return generate_test_failure_explanation(
            function_name,
            output,
        )


def answer_test_execution_question(question, analyzer):
    question_lower = question.lower()

    execution_phrases = [
        "run tests",
        "run test",
        "execute tests",
        "execute test",
        "show test results",
        "run pytest",
    ]

    if not any(
        phrase in question_lower
        for phrase in execution_phrases
    ):
        return None

    function_name = None

    if "get_user" in question_lower:
        function_name = "get_user"
    elif "connect_database" in question_lower:
        function_name = "connect_database"

    if function_name is None:
        return (
            "Please specify a supported function: "
            "`get_user()` or `connect_database()`."
        )

    result = analyzer.run_tests(function_name)

    if not result["success"]:
        details = result.get("message") or result.get("errors", "")
        return (
            "## Test Execution Failed\n\n"
            f"{details or 'The test command returned a failure.'}"
        )

    output = result.get("output", "")

    return (
        f"## Test Results: `{function_name}()`\n\n"
        "The test command completed successfully.\n\n"
        "```text\n"
        f"{output.strip()}\n"
        "```"
    )


def answer_test_generation_question(question, analyzer):
    question_lower = question.lower()

    generation_phrases = [
        "generate tests",
        "generate test file",
        "create tests",
        "create test file",
        "create pytest tests",
        "generate pytest",
        "write tests for",
        "save test cases",
    ]

    if not any(
        phrase in question_lower
        for phrase in generation_phrases
    ):
        return None

    function_name = None

    if "get_user" in question_lower:
        function_name = "get_user"
    elif "connect_database" in question_lower:
        function_name = "connect_database"

    if function_name is None:
        return (
            "Please specify a supported function: "
            "`get_user()` or `connect_database()`."
        )

    result = analyzer.generate_test_file(function_name)

    if not result["success"]:
        return (
            "## Test Generation\n\n"
            f"{result['message']}"
        )

    return (
        "## Test File Generated Successfully\n\n"
        f"**Function:** `{function_name}()`\n\n"
        f"**File:** `{result['file']}`\n\n"
        f"{result['message']}\n\n"
        "**Run the tests in Terminal:**\n\n"
        f"```bash\npython -m pytest {result['file']} -v\n```"
    )


def answer_test_suggestion_question(question, analyzer):
    question_lower = question.lower()

    test_phrases = [
        "suggest tests",
        "suggest test cases",
        "what should i test",
        "generate test scenarios",
        "test cases for",
        "tests for",
    ]

    if not any(phrase in question_lower for phrase in test_phrases):
        return None

    function_name = None

    if "get_user" in question_lower:
        function_name = "get_user"
    elif "connect_database" in question_lower:
        function_name = "connect_database"

    if function_name is None:
        return (
            "Please specify a supported function: "
            "`get_user()` or `connect_database()`."
        )

    report = analyzer.suggest_tests(function_name)

    if not report["tests"]:
        return report["message"]

    lines = [
        f"## Suggested Tests: `{function_name}()`",
        "",
    ]

    for index, test in enumerate(report["tests"], start=1):
        lines.extend([
            f"### {index}. {test['scenario']}",
            f"**Expected result:** {test['expected']}",
            "",
        ])

    lines.append(f"**Note:** {report['message']}")

    return "\n".join(lines)


def answer_change_impact_question(question, analyzer):
    question_lower = question.lower()

    impact_phrases = [
        "change impact",
        "impact of changing",
        "what happens if i change",
        "what files might be affected",
        "which files are affected",
        "what depends on",
        "impact analysis",
        "affected if i modify",
    ]

    if not any(
        phrase in question_lower
        for phrase in impact_phrases
    ):
        return None

    function_name = None

    if "get_user" in question_lower:
        function_name = "get_user"
    elif "connect_database" in question_lower:
        function_name = "connect_database"

    if function_name is None:
        return (
            "Please specify a supported function, such as "
            "`get_user()` or `connect_database()`."
        )

    report = analyzer.analyze_change_impact(function_name)

    lines = [
        f"## Change Impact Analysis: `{function_name}()`",
        "",
        "### Direct callers",
    ]

    callers = report["direct_callers"]

    if callers:
        for caller in callers:
            lines.append(
                f"- `{caller['function']}()` in "
                f"`{caller['file_path']}`, line {caller['line']}"
            )
    else:
        lines.append("- No direct callers were detected.")

    lines.extend(["", "### Import dependencies"])

    imports = report["imported_by"]

    if imports:
        for item in imports:
            lines.append(
                f"- `{item['file']}` imports "
                f"`{function_name}()` from `{item['module']}` "
                f"at line {item['line']}"
            )
    else:
        lines.append("- No matching imports were detected.")

    lines.extend(["", "### Potentially affected files"])

    affected_files = report["potentially_affected_files"]

    if affected_files:
        lines.extend(f"- `{file_name}`" for file_name in affected_files)
    else:
        lines.append("- No files containing direct callers were detected.")

    lines.extend([
        "",
        "**Limitations:** This is a static estimate based on detected "
        "calls and imports. It does not prove that a change will break "
        "the application or identify every indirect dependency.",
    ])

    return "\n".join(lines)


def answer_bug_scan_question(question, analyzer):
    question_lower = question.lower()

    bug_scan_phrases = [
        "find bugs",
        "detect bugs",
        "scan for bugs",
        "scan my code",
        "find potential problems",
        "code quality warnings",
        "run bug detection",
        "potential problems in this repository",
        "review my code",
    ]

    if not any(
        phrase in question_lower for phrase in bug_scan_phrases
    ):
        return None

    findings = analyzer.detect_basic_bugs()

    if not findings:
        return (
            "## Static Analysis Results\n\n"
            "**Status:** Completed\n\n"
            "No issues matching the current detection rules were found.\n\n"
            "**Limitations:** This scanner currently checks for "
            "comparisons with `None` using `==` or `!=`, and bare "
            "`except:` clauses. It does not detect every possible bug."
        )

    lines = [
        "## Static Analysis Results",
        "",
        f"**Issues found:** {len(findings)}",
    ]

    for finding in findings:
        lines.extend([
            "",
            f"### {finding['severity']}",
            f"**File:** `{finding['file']}`",
            f"**Line:** {finding.get('line', 'N/A')}",
            f"**Finding:** {finding['issue']}",
        ])

    return "\n".join(lines)


def answer_structural_question(question, analyzer):
    """
    Answer common repository-structure questions using
    static analysis instead of LLM-generated guesses.
    """

    question_lower = question.lower().strip()

    # Find callers of a named function.
    known_functions = [
        "get_user",
        "connect_database",
        "main",
    ]

    if (
        "who calls" in question_lower
        or "where is" in question_lower
        or "which files call" in question_lower
        or "where does" in question_lower
    ):

        for function_name in known_functions:

            if function_name in question_lower:

                callers = analyzer.find_function_callers(
                    function_name
                )

                if not callers:
                    return (
                        f"No calls to `{function_name}()` "
                        "were found in the analyzed Python files."
                    )

                lines = [
                    f"Found calls to `{function_name}()`:"
                ]

                for caller in callers:
                    lines.append(
                        f"- `{caller['file_path']}` "
                        f"at line {caller['line']}"
                    )

                return "\n".join(lines)

    return None


def answer_function_behavior_question(question, analyzer):
    question_lower = question.lower()

    known_functions = [
        "get_user",
        "connect_database",
        "main",
    ]

    asks_about_return = any(
        phrase in question_lower
        for phrase in [
            "what does",
            "what is",
            "return",
            "returns",
        ]
    )

    if not asks_about_return:
        return None

    for function_name in known_functions:

        if function_name in question_lower:

            return analyzer.explain_function_behavior(
                function_name
            )

    return None


# ---------------------------------
# Generate grounded answers
# ---------------------------------

def generate_answer(question, chunks):

    if not chunks:
        return (
            "I couldn't find sufficiently relevant source code "
            "to answer this question reliably. "
            "Try asking a more specific question."
        )

    context_parts = []

    for chunk in chunks:

        context_parts.append(
            f"""
FILE: {chunk['file_path']}
LINES: {chunk['start_line']}-{chunk['end_line']}

SOURCE CODE:
{chunk['text']}
"""
        )

    context = "\n\n".join(context_parts)

    system_prompt = """
You are an AI software engineer analyzing a source-code repository.

Answer questions using the supplied source code.

RULES:

1. Read the supplied code carefully before answering.

2. State conclusions that directly follow from the code.

3. Never invent files, functions, variables, libraries, APIs,
   database connections, or application features.

4. Distinguish between what the code implements and what its names
   or printed messages merely suggest.

5. If a function only prints "Database connection established"
   and contains no connection logic, explain that the shown function
   does not implement a real database connection.

6. Do not claim that the entire repository lacks a feature unless
   the available evidence covers the relevant implementation.

7. If the evidence supports a partial answer, provide that answer
   and identify any remaining uncertainty.

8. Use "I couldn't verify this from the retrieved source code"
   only when the retrieved evidence genuinely does not answer
   the question.

9. Cite the actual file paths and line ranges provided in the context.
   Never invent citations or line numbers.

10. Be direct, factual, and concise.

11. Do not repeat uncertainty disclaimers when the code clearly
    supports a conclusion.
"""

    user_prompt = f"""
QUESTION:
{question}

RETRIEVED REPOSITORY CONTEXT:
{context}

Answer using only the evidence above.
"""

    response = ollama.chat(
        model=LLM_MODEL,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        options={
            "temperature": 0,
            "num_ctx": 4096,
        },
    )

    return response["message"]["content"]

def generate_bug_analysis(question, chunks):

    if not chunks:
        return (
            "## Investigation Result\n\n"
            "I couldn't retrieve sufficiently relevant source code "
            "to investigate this issue. Please provide the affected "
            "file, function, or error message."
        )

    context_parts = []

    for chunk in chunks:
        context_parts.append(
            f"""
FILE: {chunk['file_path']}
LINES: {chunk['start_line']}-{chunk['end_line']}

SOURCE CODE:
{chunk['text']}
"""
        )

    context = "\n\n".join(context_parts)

    system_prompt = """
You are a careful software debugging assistant.

Investigate the reported issue using only the supplied source code.

Return these sections:

## 1. Observed Behavior
Describe what the supplied code actually does.

## 2. Evidence
Cite the supplied file paths and line ranges.

## 3. Confirmed Problems
List only problems directly supported by the code.

If no bug is established, explicitly say so.

## 4. Potential Problems
Describe plausible risks separately from confirmed problems.

## 5. Suggested Fix
Suggest a minimal change only when the evidence justifies it.

## 6. Verification
Give a test that would help verify the diagnosis.

## 7. Confidence
Choose High, Medium, or Low and explain why.

STRICT RULES:

1. Never invent source code or claim that unseen code exists.
2. Never invent a runtime exception. Explain the conditions
   required for an exception to occur.
3. Do not assume that a function returns None, raises an exception,
   or returns a particular user unless the supplied code proves it.
4. Do not infer that a dictionary contains a particular user ID
   unless the dictionary contents are supplied.
5. A function that prints a connection message does not necessarily
   establish a real database connection.
6. Distinguish observed behavior from expected behavior.
7. If a question concerns a function, prioritize the function's
   implementation over unrelated retrieved code.
8. If the retrieved evidence is insufficient, say exactly
   what information is missing.
9. Do not propose arbitrary changes just to provide a solution.
10. Never claim a suggested fix has been tested.
"""

    response = ollama.chat(
        model=LLM_MODEL,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": (
                    f"INVESTIGATION REQUEST:\n{question}\n\n"
                    f"SUPPLIED SOURCE CODE:\n{context}"
                ),
            },
        ],
        options={
            "temperature": 0,
            "num_ctx": 4096,
        },
    )

    return response["message"]["content"]


def get_function_facts(analyzer, function_name):
    """Return deterministic facts about a specific function."""

    return analyzer.explain_function_behavior(function_name)


def answer_deterministic_investigation(question, analyzer):
    question_lower = question.lower()

    if "connect_database" in question_lower:
        facts = analyzer.explain_function_behavior(
            "connect_database"
        )

        return (
            "## Investigation Report\n\n"
            "**Function:** `connect_database()`\n\n"
            "**Conclusion:** The analyzed function does not "
            "implement a real database connection.\n\n"
            "**Evidence:**\n"
            "- The function calls `print()`.\n"
            "- No recognized database connection API was detected.\n\n"
            "**Return behavior:**\n"
            "The function has no explicit return statement, so it "
            "returns `None` if it completes normally.\n\n"
            "**Limitations:**\n"
            "This conclusion describes the analyzed function. "
            "It does not establish whether other parts of the "
            "application create a database connection.\n\n"
            "**Analyzer details:**\n"
            f"{facts}"
        )

    if (
        "get_user" in question_lower
        and any(
            phrase in question_lower
            for phrase in [
                "missing",
                "doesn't exist",
                "does not exist",
                "not exist",
                "unknown user",
            ]
        )
    ):
        facts = analyzer.explain_function_behavior("get_user")

        return (
            "## Investigation Report\n\n"
            "**Function:** `get_user()`\n\n"
            "**Conclusion:** An unknown user ID causes "
            "`users.get(user_id)` to return `None`.\n\n"
            "**Evidence:**\n"
            "- The function uses dictionary `get()`.\n"
            "- No default value is supplied to `get()`.\n\n"
            "**Impact:**\n"
            "The caller must handle the possibility of `None` "
            "before accessing user fields. In the current "
            "sample `main.py`, the caller checks `if user:` "
            "before accessing `user['name']`.\n\n"
            "**Confirmed bug:** None established by this behavior.\n\n"
            "**Analyzer details:**\n"
            f"{facts}"
        )

    return None


def generate_test_failure_explanation(
    function_name,
    failure_report,
):
    """Explain test failures using actual pytest evidence."""

    system_prompt = """
You are a careful Python test failure analysis assistant.

Explain test failures using only the supplied pytest report.

Structure your response as follows:

## 1. Test Failure
Identify the failing test and error message.

## 2. What Happened
Explain what the test output confirms.

## 3. Likely Cause
Explain the likely cause only when supported by the evidence.
Clearly label any hypothesis as a possibility.

## 4. What to Investigate
Suggest specific checks based on the available evidence.

## 5. Verification
Suggest how to verify the explanation.

STRICT RULES:
1. Treat the pytest output as the source of truth about the reported failure.
2. Do not invent source code, variables, or runtime behavior.
3. Distinguish confirmed facts from hypotheses.
4. Do not claim that a proposed fix has been tested.
5. If all tests passed, state that there is no failure to explain.
6. Do not claim that a test failure proves the application itself is incorrect.
"""

    response = ollama.chat(
        model=LLM_MODEL,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": (
                    f"Function under test: {function_name}\n\n"
                    "Actual pytest failure report:\n"
                    f"{failure_report}\n\n"
                    "Explain the failure using only this evidence."
                ),
            },
        ],
        options={
            "temperature": 0,
            "num_ctx": 4096,
        },
    )

    return response["message"]["content"]


def generate_verified_investigation(
    question,
    chunks,
    analyzer,
):
    """
    Combine source-code retrieval and static-analysis facts
    before asking the LLM to investigate an issue.
    """

    question_lower = question.lower()

    # Identify a function mentioned in the question.
    known_functions = [
        "get_user",
        "connect_database",
    ]

    target_function = next(
        (
            name
            for name in known_functions
            if name in question_lower
        ),
        None,
    )

    function_findings = (
        analyzer.inspect_function(target_function)
        if target_function
        else []
    )

    verified_facts = (
        get_function_facts(analyzer, target_function)
        if target_function
        else "No matching function was identified by static analysis."
    )

    # When a function is named, keep only retrieved chunks overlapping
    # that function's own source range. Other chunks are not evidence
    # about the named function.
    if target_function and function_findings:
        chunks = [
            chunk
            for chunk in chunks
            if any(
                chunk["file_path"] == finding["file"]
                and chunk["start_line"] <= finding["end_line"]
                and chunk["end_line"] >= finding["start_line"]
                for finding in function_findings
            )
        ]
    elif target_function:
        chunks = []

    source_context = "\n\n".join(
        f"""
FILE: {chunk['file_path']}
LINES: {chunk['start_line']}-{chunk['end_line']}

CODE:
{chunk['text']}
"""
        for chunk in chunks
    )

    if not source_context:
        source_context = "No source chunks were retrieved."

    system_prompt = """
You are a code investigation assistant.

Use only the supplied source code and analyzer findings.

STRICT RULES:

1. Use only the supplied source code and analyzer findings.
2. Do not attribute behavior from one function to another.
3. Do not claim that a function has a bug without supporting evidence.
4. Do not call an implicit None return a bug unless the caller
   demonstrates a problem caused by that return value.
5. Do not recommend dictionary access, database operations,
   error handling, or thread synchronization unless relevant
   to the question and supported by evidence.
6. Separate confirmed observations from potential risks.
7. If evidence is insufficient, explicitly say so.
8. Never invent source-code behavior.
"""

    response = ollama.chat(
        model=LLM_MODEL,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": f"""
INVESTIGATION REQUEST:
{question}

STATIC ANALYSIS FACTS:
{verified_facts}

RETRIEVED SOURCE CODE:
{source_context}

Produce a concise investigation with:
- Observed behavior
- Evidence
- Confirmed problems
- Potential problems
- Suggested fix, if justified
- Verification
- Confidence
""",
            },
        ],
        options={
            "temperature": 0,
            "num_ctx": 4096,
        },
    )

    return response["message"]["content"]


def retrieve_for_investigation(rag, question):

    question_lower = question.lower()

    function_files = {
        "get_user": "users.py",
        "connect_database": "database.py",
        "main": "main.py",
    }

    target_file = None

    for function_name, file_name in function_files.items():
        if function_name in question_lower:
            target_file = file_name
            break

    chunks = rag.retrieve(
        question,
        top_k=TOP_K,
        min_similarity=MIN_SIMILARITY,
    )

    # Prioritize the target file when the question names a known
    # function. Keep other retrieved chunks as supporting evidence.
    if target_file:
        chunks.sort(
            key=lambda chunk: (
                chunk["file_path"] != target_file,
                -chunk.get("similarity", 0.0),
            )
        )

    return chunks


# ---------------------------------
# Sidebar
# ---------------------------------

st.sidebar.title("🤖 Codebase AI")

st.sidebar.write(
    "Understand software repositories "
    "using a locally running language model."
)

st.sidebar.markdown("---")

st.sidebar.subheader("Configuration")

st.sidebar.write(f"**LLM:** {LLM_MODEL}")
st.sidebar.write("**Embeddings:** all-MiniLM-L6-v2")
st.sidebar.write("**Vector database:** ChromaDB")
st.sidebar.write("**Retrieval:** Semantic search")

if st.sidebar.button("Clear conversation"):

    st.session_state.messages = []

    st.rerun()


show_debug = st.sidebar.toggle(
    "Show retrieval scores",
    value=False,
)


# ---------------------------------
# Main application
# ---------------------------------

st.title("🤖 AI Knowledge Transfer Agent")

st.caption(
    "Ask questions about your codebase using local AI and RAG."
)

st.info(
    "Current repository: sample_project"
)

with st.expander("How does this application work?"):

    st.markdown(
        """
        1. Reads supported source files.
        2. Splits source code into chunks.
        3. Generates vector embeddings.
        4. Retrieves potentially relevant code from ChromaDB.
        5. Sends the retrieved code to a local LLM.
        6. Generates an answer with source references.

        **Important:** Retrieved code is evidence for the answer,
        but retrieval similarity alone does not guarantee correctness.
        """
    )


# ---------------------------------
# Initialize RAG
# ---------------------------------

try:

    with st.spinner("Loading the codebase index..."):

        rag = load_rag_engine()

    st.success(
        f"Codebase ready: {rag.collection.count()} indexed chunks."
    )

except Exception as error:

    st.error("Could not initialize the codebase index.")

    st.exception(error)

    st.stop()


# ---------------------------------
# Initialize chat history
# ---------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []


# ---------------------------------
# Display previous messages
# ---------------------------------

for message in st.session_state.messages:

    with st.chat_message(message["role"]):

        st.markdown(message["content"])

        if message.get("sources"):

            with st.expander("View retrieved source code"):

                for source in message["sources"]:

                    st.markdown(
                        f"**{source['file_path']}** "
                        f"(lines {source['start_line']}-"
                        f"{source['end_line']})"
                    )

                    st.code(source["text"], language="python")

                    if show_debug:
                        st.caption(
                            f"Cosine similarity: "
                            f"{source['similarity']:.3f}"
                        )


# ---------------------------------
# User input
# ---------------------------------

question = st.chat_input(
    "Ask something about the codebase..."
)

if question:

    st.session_state.messages.append(
        {
            "role": "user",
            "content": question,
        }
    )

    with st.chat_message("user"):
        st.markdown(question)

    try:

        # Initialize defaults so every question path works.
        chunks = []
        sources = []

        with st.spinner("Searching code and generating an answer..."):

            analyzer = load_code_analyzer()

            question_lower = question.lower()

            bug_keywords = [
                "debug",
                "bug",
                "error",
                "exception",
                "crash",
                "failure",
                "fix",
                "root cause",
                "investigate",
                "not working",
            ]

            is_bug_question = any(
                keyword in question_lower
                for keyword in bug_keywords
            )

            failure_explanation = answer_test_failure_explanation_question(
                question,
                analyzer,
            )

            if failure_explanation is not None:
                answer = failure_explanation
                chunks = []
                sources = []
            else:
                scan_answer = answer_bug_scan_question(
                    question,
                    analyzer,
                )

                if scan_answer is not None:

                    answer = scan_answer
                    chunks = []

                elif is_bug_question:

                    deterministic_answer = answer_deterministic_investigation(
                        question,
                        analyzer,
                    )

                    if deterministic_answer is not None:

                        answer = deterministic_answer
                        chunks = []

                    else:

                        chunks = retrieve_for_investigation(
                            rag,
                            question,
                        )

                        answer = generate_verified_investigation(
                            question,
                            chunks,
                            analyzer,
                        )

                else:

                    execution_answer = answer_test_execution_question(
                        question,
                        analyzer,
                    )

                    if execution_answer is not None:
                        test_answer = execution_answer
                    else:
                        generation_answer = answer_test_generation_question(
                            question,
                            analyzer,
                        )

                        if generation_answer is not None:
                            test_answer = generation_answer
                        else:
                            test_answer = answer_test_suggestion_question(
                                question,
                                analyzer,
                            )

                    if test_answer is not None:

                        answer = test_answer
                        chunks = []

                    else:

                        impact_answer = answer_change_impact_question(
                            question,
                            analyzer,
                        )

                        if impact_answer is not None:

                            answer = impact_answer
                            chunks = []

                        else:

                            dependency_answer = answer_dependency_question(
                                question,
                                analyzer,
                            )

                            if dependency_answer is not None:

                                answer = dependency_answer
                                chunks = []

                            else:

                                caller_answer = answer_caller_analysis_question(
                                    question,
                                    analyzer,
                                )

                                if caller_answer is not None:

                                    answer = caller_answer
                                    chunks = []

                                else:

                                    behavior_answer = answer_function_behavior_question(
                                        question,
                                        analyzer,
                                    )

                                    if behavior_answer is not None:

                                        answer = behavior_answer
                                        chunks = []

                                    else:

                                        flow_answer = answer_execution_flow_question(
                                            question,
                                            analyzer,
                                        )

                                        if flow_answer is not None:

                                            answer = flow_answer
                                            chunks = []

                                        else:

                                            structural_answer = answer_structural_question(
                                                question,
                                                analyzer,
                                            )

                                            if structural_answer is not None:

                                                answer = structural_answer
                                                chunks = []

                                            else:

                                                chunks = rag.retrieve(
                                                    question,
                                                    top_k=TOP_K,
                                                    min_similarity=MIN_SIMILARITY,
                                                )

                                                answer = generate_answer(
                                                    question,
                                                    chunks,
                                                )

        # Prepare source information for every question path.
        sources = [
            {
                "file_path": chunk["file_path"],
                "start_line": chunk["start_line"],
                "end_line": chunk["end_line"],
                "text": chunk["text"],
                "similarity": chunk.get("similarity", 0.0),
            }
            for chunk in chunks
        ]

        # Display the assistant response for every question path.
        with st.chat_message("assistant"):

            st.markdown(answer)

            if sources:

                with st.expander("View retrieved source code"):

                    for source in sources:

                        st.markdown(
                            f"**{source['file_path']}** "
                            f"(lines {source['start_line']}-"
                            f"{source['end_line']})"
                        )

                        st.code(
                            source["text"],
                            language="python",
                        )

                        if show_debug:
                            st.caption(
                                "Cosine similarity: "
                                f"{source['similarity']:.3f}"
                            )

        # Save the assistant response.
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": answer,
                "sources": sources,
            }
        )

    except Exception as error:

        st.error(
            f"Something went wrong: {error}"
        )

        with st.expander("Error details"):
            st.exception(error)
