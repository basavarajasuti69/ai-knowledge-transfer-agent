import ast
import subprocess
import sys
from pathlib import Path


class CodeAnalyzer:
    """Analyze imports, functions, and function calls in Python files."""

    def __init__(self, project_path="sample_project"):
        self.project_path = Path(project_path)

    def analyze(self):
        """Analyze every Python file in the project."""

        if not self.project_path.exists():
            raise FileNotFoundError(
                f"Project not found: {self.project_path.resolve()}"
            )

        files = {}

        for path in self.project_path.rglob("*.py"):
            relative_path = path.relative_to(
                self.project_path
            ).as_posix()

            try:
                source = path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
                tree = ast.parse(source)

            except (OSError, SyntaxError) as error:
                print(f"Could not analyze {path}: {error}")
                continue

            imports = []
            functions = []
            calls = []

            for node in ast.walk(tree):

                # Identify import statements.
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)

                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""

                    for alias in node.names:
                        imports.append(
                            f"{module}.{alias.name}".strip(".")
                        )

                # Identify function definitions.
                elif isinstance(
                    node,
                    (
                        ast.FunctionDef,
                        ast.AsyncFunctionDef,
                    ),
                ):
                    functions.append({
                        "name": node.name,
                        "line": node.lineno,
                    })

                # Identify function and method calls.
                elif isinstance(node, ast.Call):

                    if isinstance(node.func, ast.Name):
                        call_name = node.func.id

                    elif isinstance(node.func, ast.Attribute):
                        call_name = node.func.attr

                    else:
                        continue

                    calls.append({
                        "name": call_name,
                        "line": node.lineno,
                    })

            files[relative_path] = {
                "imports": sorted(set(imports)),
                "functions": functions,
                "calls": calls,
            }

        return files

    def format_report(self):
        """Generate a readable repository analysis report."""

        analysis = self.analyze()
        report = []

        for file_path, details in analysis.items():

            report.append(f"FILE: {file_path}")

            report.append("IMPORTS:")

            if details["imports"]:
                for item in details["imports"]:
                    report.append(f"  - {item}")
            else:
                report.append("  - No imports found")

            report.append("FUNCTIONS:")

            if details["functions"]:
                for function in details["functions"]:
                    report.append(
                        f"  - {function['name']} "
                        f"(line {function['line']})"
                    )
            else:
                report.append("  - No functions found")

            report.append("FUNCTION CALLS:")

            if details["calls"]:
                for call in details["calls"]:
                    report.append(
                        f"  - {call['name']} "
                        f"(line {call['line']})"
                    )
            else:
                report.append("  - No calls found")

            report.append("")

        return "\n".join(report)

    def find_function_callers(self, function_name):
        """Find Python files containing calls to a function."""

        analysis = self.analyze()
        callers = []

        for file_path, details in analysis.items():
            for call in details["calls"]:
                if call["name"] == function_name:
                    callers.append({
                        "file_path": file_path,
                        "function": function_name,
                        "line": call["line"],
                    })

        return callers

    def inspect_function(self, function_name):
        """Return source-level facts about a named Python function."""

        results = []

        for path in self.project_path.rglob("*.py"):

            try:
                source = path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
                tree = ast.parse(source)

            except (OSError, SyntaxError):
                continue

            for node in ast.walk(tree):

                if not isinstance(
                    node,
                    (
                        ast.FunctionDef,
                        ast.AsyncFunctionDef,
                    ),
                ):
                    continue

                if node.name != function_name:
                    continue

                facts = {
                    "file": path.relative_to(
                        self.project_path
                    ).as_posix(),
                    "function": node.name,
                    "start_line": node.lineno,
                    "end_line": node.end_lineno,
                    "uses_dict_get": False,
                    "uses_dictionary_subscript": False,
                    "prints_message": False,
                    "calls_connection_api": False,
                    "return_expressions": [],
                }

                for child in ast.walk(node):

                    if isinstance(child, ast.Call):

                        if isinstance(child.func, ast.Attribute):
                            if child.func.attr == "get":
                                facts["uses_dict_get"] = True

                            if child.func.attr in {
                                "connect",
                                "create_engine",
                                "connect_async",
                            }:
                                facts["calls_connection_api"] = True

                        elif isinstance(child.func, ast.Name):

                            if child.func.id == "print":
                                facts["prints_message"] = True

                            if child.func.id == "connect":
                                facts["calls_connection_api"] = True

                    if isinstance(child, ast.Subscript):
                        facts["uses_dictionary_subscript"] = True

                    if isinstance(child, ast.Return):
                        facts["return_expressions"].append(
                            ast.unparse(child.value)
                            if child.value is not None
                            else "None"
                        )

                results.append(facts)

        return results

    def explain_function_behavior(self, function_name):
        """
        Describe observable source-level behavior without
        relying on an LLM to infer basic Python semantics.
        """

        findings = self.inspect_function(function_name)

        if not findings:
            return (
                f"No function named '{function_name}' "
                "was found in the analyzed Python files."
            )

        reports = []

        for item in findings:

            lines = [
                f"Function: {item['function']}()",
                f"File: {item['file']}",
                (
                    f"Lines: {item['start_line']}-"
                    f"{item['end_line']}"
                ),
            ]

            if item["prints_message"]:
                lines.append(
                    "Print behavior: Calls print(). "
                    "Printed text is not the function's return value."
                )

            if item["uses_dict_get"]:
                lines.append(
                    "Dictionary lookup: Uses dict.get(). "
                    "For a missing key, dict.get() returns None "
                    "when no default is supplied."
                )

            if item["return_expressions"]:
                lines.append(
                    "Explicit return expressions: "
                    + ", ".join(item["return_expressions"])
                )
            else:
                lines.append(
                    "Return behavior: No explicit return statement "
                    "was detected in the function. If it completes "
                    "normally, it returns None."
                )

            if item["calls_connection_api"]:
                lines.append(
                    "Connection analysis: A recognized connection "
                    "API call was detected. Inspect its arguments "
                    "and behavior before concluding that a connection "
                    "was successfully established."
                )
            else:
                lines.append(
                    "Connection analysis: No recognized connection "
                    "API call was detected by this analyzer. "
                    "This alone does not rule out indirect connections."
                )

            reports.append("\n".join(lines))

        return "\n\n".join(reports)

    def explain_execution_flow(self):
        """Explain the application's execution flow using AST analysis."""

        entry_file = self.project_path / "main.py"

        if not entry_file.exists():
            return "Could not find main.py in the analyzed project."

        try:
            source = entry_file.read_text(encoding="utf-8")
        except OSError as error:
            return f"Could not read main.py: {error}"

        try:
            tree = ast.parse(source)
        except SyntaxError as error:
            return f"Could not analyze main.py: {error}"

        flow = [
            "APPLICATION EXECUTION FLOW",
            "=" * 30,
            "Entry file: main.py",
        ]

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue

            if node.name != "main":
                continue

            flow.append("\n1. Execution starts in main().")

            for statement in node.body:
                if isinstance(statement, ast.Expr):
                    value = statement.value

                    if isinstance(value, ast.Call):
                        if isinstance(value.func, ast.Name):
                            function_name = value.func.id

                            if function_name == "connect_database":
                                flow.append(
                                    "2. connect_database() is called."
                                )
                                flow.append(
                                    "   It prints a message; "
                                    "the current implementation does not "
                                    "establish a real database connection."
                                )

                elif isinstance(statement, ast.Assign):
                    value = statement.value

                    if (
                        isinstance(value, ast.Call)
                        and isinstance(value.func, ast.Name)
                        and value.func.id == "get_user"
                    ):
                        flow.append(
                            "3. get_user(1) is called and its result "
                            "is assigned to user."
                        )

                elif isinstance(statement, ast.If):
                    flow.append(
                        "4. The application checks whether user exists."
                    )
                    flow.append(
                        "   If true, it prints a welcome message."
                    )
                    flow.append(
                        "   Otherwise, it prints 'User not found.'"
                    )

        if len(flow) == 3:
            flow.append(
                "No main() function was found in the expected form."
            )

        return "\n".join(flow)

    def detect_basic_bugs(self):
        """Detect a few common Python code issues using AST."""

        findings = []

        for file_path in self.project_path.rglob("*.py"):
            try:
                source = file_path.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (SyntaxError, UnicodeDecodeError) as error:
                findings.append({
                    "file": str(file_path),
                    "issue": f"Could not analyze file: {error}",
                    "severity": "Warning",
                })
                continue

            for node in ast.walk(tree):

                # Detect equality comparisons against None using ==.
                if isinstance(node, ast.Compare):
                    has_none = (
                        isinstance(node.left, ast.Constant)
                        and node.left.value is None
                    ) or any(
                        isinstance(comparator, ast.Constant)
                        and comparator.value is None
                        for comparator in node.comparators
                    )

                    if has_none and any(
                        isinstance(op, (ast.Eq, ast.NotEq))
                        for op in node.ops
                    ):
                        findings.append({
                            "file": str(file_path),
                            "line": node.lineno,
                            "issue": (
                                "Comparison with None using == or !=. "
                                "Consider using 'is None' or 'is not None'."
                            ),
                            "severity": "Suggestion",
                        })

                # Detect bare except clauses.
                if isinstance(node, ast.ExceptHandler):
                    if node.type is None:
                        findings.append({
                            "file": str(file_path),
                            "line": node.lineno,
                            "issue": (
                                "Bare except clause catches nearly all "
                                "exceptions and can hide unexpected errors."
                            ),
                            "severity": "Warning",
                        })

        return findings

    def analyze_function_callers(self, function_name):
        """Find callers and inspect how they use the function result."""

        callers = self.find_function_callers(function_name)
        results = []

        for caller in callers:
            file_path = self.project_path / caller["file_path"]

            try:
                source = file_path.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue

                for child in ast.walk(node):
                    if not isinstance(child, ast.Call):
                        continue

                    if not (
                        isinstance(child.func, ast.Name)
                        and child.func.id == function_name
                    ):
                        continue

                    assigned_variable = None

                    for statement in ast.walk(node):
                        if (
                            isinstance(statement, ast.Assign)
                            and statement.value is child
                        ):
                            if (
                                len(statement.targets) == 1
                                and isinstance(
                                    statement.targets[0], ast.Name
                                )
                            ):
                                assigned_variable = statement.targets[0].id

                    null_check_found = False

                    if assigned_variable:
                        for statement in ast.walk(node):
                            if not isinstance(statement, ast.If):
                                continue

                            test = statement.test

                            if (
                                isinstance(test, ast.Name)
                                and test.id == assigned_variable
                            ):
                                null_check_found = True
                                break

                    results.append({
                        "file": caller["file_path"],
                        "caller": node.name,
                        "line": child.lineno,
                        "assigned_variable": assigned_variable,
                        "truthiness_check_found": null_check_found,
                    })

        return results

    def analyze_dependencies(self):
        """Identify local Python module imports."""

        dependencies = []

        for file_path in self.project_path.rglob("*.py"):
            try:
                source = file_path.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue

            relative_file = file_path.relative_to(
                self.project_path
            ).as_posix()

            for node in ast.walk(tree):

                if isinstance(node, ast.Import):
                    for alias in node.names:
                        dependencies.append({
                            "file": relative_file,
                            "module": alias.name,
                            "imported_names": [],
                            "line": node.lineno,
                        })

                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""

                    dependencies.append({
                        "file": relative_file,
                        "module": module,
                        "imported_names": [
                            alias.name for alias in node.names
                        ],
                        "line": node.lineno,
                    })

        return dependencies

    def analyze_change_impact(self, function_name):
        """Identify direct callers and imports related to a function."""

        callers = self.find_function_callers(function_name)
        dependencies = self.analyze_dependencies()

        # Find modules that import the target function.
        imported_by = []

        for dependency in dependencies:
            if function_name in dependency["imported_names"]:
                imported_by.append({
                    "file": dependency["file"],
                    "module": dependency["module"],
                    "line": dependency["line"],
                })

        # Collect files containing direct callers.
        affected_files = sorted({
            caller["file_path"]
            for caller in callers
        })

        return {
            "function": function_name,
            "direct_callers": callers,
            "imported_by": imported_by,
            "potentially_affected_files": affected_files,
        }

    def suggest_tests(self, function_name):
        """Suggest tests based on detected function behavior."""

        findings = self.inspect_function(function_name)

        if not findings:
            return {
                "function": function_name,
                "tests": [],
                "message": "Function not found in the analyzed project.",
            }

        tests = []

        for item in findings:
            if function_name == "get_user":
                tests.extend([
                    {
                        "scenario": "Valid user ID",
                        "expected": (
                            "The function returns the corresponding "
                            "user dictionary."
                        ),
                    },
                    {
                        "scenario": "Unknown user ID",
                        "expected": (
                            "The function returns None because "
                            "dict.get() has no default value."
                        ),
                    },
                    {
                        "scenario": "Returned user fields",
                        "expected": (
                            "A valid result contains the expected "
                            "name and role fields."
                        ),
                    },
                ])

            elif function_name == "connect_database":
                tests.extend([
                    {
                        "scenario": "Function return value",
                        "expected": (
                            "The current function returns None "
                            "when it completes normally."
                        ),
                    },
                    {
                        "scenario": "Printed output",
                        "expected": (
                            "The function prints "
                            "'Database connection established.'"
                        ),
                    },
                ])

        if not tests:
            tests.append({
                "scenario": "Basic execution",
                "expected": (
                    "Verify that the function executes successfully "
                    "with representative inputs."
                ),
            })

        return {
            "function": function_name,
            "tests": tests,
            "message": (
                "These are suggested tests, not executed test results."
            ),
        }

    def generate_test_file(self, function_name):
        """Generate pytest tests for supported sample-project functions."""

        if function_name == "get_user":
            test_code = '''import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PROJECT = PROJECT_ROOT / "sample_project"

sys.path.insert(0, str(SAMPLE_PROJECT))

from users import get_user


def test_get_user_returns_rahul():
    assert get_user(1) == {
        "name": "Rahul",
        "role": "Developer",
    }


def test_get_user_returns_priya():
    assert get_user(2) == {
        "name": "Priya",
        "role": "Designer",
    }


def test_get_user_returns_none_for_unknown_id():
    assert get_user(999) is None


def test_get_user_returns_expected_fields():
    user = get_user(1)

    assert "name" in user
    assert "role" in user
'''

        elif function_name == "connect_database":
            test_code = '''import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PROJECT = PROJECT_ROOT / "sample_project"

sys.path.insert(0, str(SAMPLE_PROJECT))

from database import connect_database


def test_connect_database_prints_message(capsys):
    connect_database()

    captured = capsys.readouterr()

    assert captured.out == "Database connection established.\\n"


def test_connect_database_returns_none():
    assert connect_database() is None
'''

        else:
            return {
                "success": False,
                "message": (
                    "Automatic test generation currently supports "
                    "get_user and connect_database."
                ),
            }

        tests_dir = self.project_path.parent / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        output_path = tests_dir / f"test_{function_name}_generated.py"

        if output_path.exists():
            return {
                "success": False,
                "message": (
                    f"{output_path.name} already exists. "
                    "The existing file was not overwritten."
                ),
            }

        output_path.write_text(test_code, encoding="utf-8")

        return {
            "success": True,
            "file": str(output_path),
            "message": (
                "Test file generated. Run it with pytest "
                "to verify the tests."
            ),
        }

    def run_tests(self, function_name):
        """Run the generated pytest file for a supported function."""

        supported_functions = {
            "get_user": "test_get_user_generated.py",
            "connect_database": "test_connect_database_generated.py",
        }

        if function_name not in supported_functions:
            return {
                "success": False,
                "message": "This function is not supported for test execution.",
            }

        tests_dir = self.project_path.parent / "tests"
        test_file = tests_dir / supported_functions[function_name]

        if not test_file.exists():
            return {
                "success": False,
                "message": (
                    f"{test_file.name} does not exist. "
                    "Generate the test file first."
                ),
            }

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    str(test_file),
                    "-v",
                    "--tb=short",
                ],
                cwd=self.project_path.parent,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )

            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "output": result.stdout,
                "errors": result.stderr,
                "combined_output": result.stdout + "\n" + result.stderr,
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "message": "Test execution timed out after 60 seconds.",
            }

    def explain_test_failure(self, function_name):
        """Run tests and analyze their actual output."""

        result = self.run_tests(function_name)

        output = result.get(
            "combined_output",
            result.get("output", "") + "\n" + result.get("errors", "")
        )

        if result.get("success"):
            return (
                f"All tests passed for {function_name}. "
                "There are no test failures to explain."
            )

        if result.get("returncode") == -1:
            return (
                f"Test execution could not be completed for {function_name}.\n"
                f"Details: {output or result.get('errors', 'Unknown error')}"
            )

        analysis = self.analyze_test_failure_output(output)

        explanation = [
            f"## Test Failure Analysis: {function_name}",
            "",
            analysis["summary"],
            "",
            "### Failure Details",
        ]

        if analysis["details"]:
            explanation.extend(
                f"- {detail}" for detail in analysis["details"]
            )
        else:
            explanation.append(
                "No recognized assertion or error message was extracted."
            )

        explanation.extend([
            "",
            "### Full Pytest Output",
            output or "No output captured.",
            "",
            "Note: This analysis identifies evidence from the test output. "
            "The underlying root cause may require inspecting the relevant code.",
        ])

        return "\n".join(explanation)

    def analyze_test_failure_output(self, test_output):
        """Extract useful information from pytest failure output."""

        if not test_output or not test_output.strip():
            return {
                "failed": False,
                "summary": "No test output was provided.",
                "details": [],
            }

        lines = test_output.splitlines()
        details = []

        for line in lines:
            cleaned = line.strip()

            if (
                "AssertionError:" in cleaned
                or "Error:" in cleaned
                or "Exception:" in cleaned
                or "assert " in cleaned
                or "FAILED " in cleaned
            ):
                details.append(cleaned)

        failed = any(
            "FAILED " in line or "AssertionError:" in line
            for line in lines
        )

        if failed:
            summary = "Test failure detected. Review the extracted details."
        else:
            summary = "No recognized test failure was detected in the output."

        return {
            "failed": failed,
            "summary": summary,
            "details": details,
        }
