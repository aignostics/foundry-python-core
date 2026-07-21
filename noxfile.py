"""Nox configuration for development tasks."""

import json
import re
import sys
from pathlib import Path

import nox
from nox.command import CommandFailed

nox.options.reuse_existing_virtualenvs = True
nox.options.default_venv_backend = "uv"

LICENSES_JSON_PATH = "reports/licenses.json"
SBOM_CYCLONEDX_PATH = "reports/sbom.json"
SBOM_SPDX_PATH = "reports/sbom.spdx"
VULNERABILITIES_JSON_PATH = "reports/vulnerabilities.json"
JUNIT_XML_PREFIX = "--junitxml=reports/junit_"
UTF8 = "utf-8"


def _read_python_version() -> str:
    """Read Python version from .python-version file.

    Returns:
        str: Python version string (e.g., "3.14" or "3.14.1")

    Raises:
        FileNotFoundError: If .python-version file does not exist
        ValueError: If version format is invalid (not 2 or 3 segments)
        OSError: If reading the file fails
    """
    version_file = Path(".python-version")
    if not version_file.exists():
        print("Error: .python-version file not found")
        sys.exit(1)

    try:
        version = version_file.read_text(encoding="utf-8").strip()
    except OSError:
        print("Error: Failed to read .python-version file")
        sys.exit(1)

    if not re.match(r"^\d+\.\d+(?:\.\d+)?$", version):
        print(f"Error: Invalid Python version format in .python-version: {version}. Expected X.Y or X.Y.Z")
        sys.exit(2)

    return version


PYTHON_VERSION = _read_python_version()
TEST_PYTHON_VERSIONS = PYTHON_VERSION  # We don't do matrix testing locally


def _setup_venv(session: nox.Session, all_extras: bool = True, resolution: str | None = None) -> None:
    """Install dependencies for the given session using uv.

    Args:
        session: The nox session
        all_extras: Whether to install all extras
        resolution: Optional uv resolution strategy (e.g. ``"lowest-direct"``).  When
            set, ``--resolution <value>`` replaces ``--frozen`` so uv re-resolves
            rather than using the lockfile.
    """
    args = ["uv", "sync", "--resolution", resolution] if resolution else ["uv", "sync", "--frozen"]
    if all_extras:
        args.append("--all-extras")
    session.run_install(
        *args,
        env={
            "UV_PROJECT_ENVIRONMENT": session.virtualenv.location,
            "UV_PYTHON": str(session.python),
        },
    )


def _format_json_with_jq(session: nox.Session, path: str) -> None:
    """Format JSON file using jq for better readability.

    Args:
        session: The nox session instance
        path: Path to the JSON file to format
    """
    with Path(f"{path}.tmp").open("w", encoding="utf-8") as outfile:
        session.run("jq", ".", path, stdout=outfile, stderr=None, external=True)
        session.run("mv", f"{path}.tmp", path, stdout=outfile, stderr=None, external=True)


@nox.session(python=[PYTHON_VERSION])
def audit(session: nox.Session) -> None:
    """Run security audit and license checks."""
    _setup_venv(session, True)

    # pip-audit to check for vulnerabilities
    ignore_vulns: list[str] = []
    try:
        session.run(
            "pip-audit",
            "-f",
            "json",
            "-o",
            VULNERABILITIES_JSON_PATH,
            *[arg for v in ignore_vulns for arg in ("--ignore", v)],
        )
        _format_json_with_jq(session, VULNERABILITIES_JSON_PATH)
    except CommandFailed:
        _format_json_with_jq(session, VULNERABILITIES_JSON_PATH)
        session.log(f"pip-audit found vulnerabilities - see {VULNERABILITIES_JSON_PATH} for details")
        session.run(  # Retry without JSON for readable output
            "pip-audit", *[arg for v in ignore_vulns for arg in ("--ignore", v)]
        )

    # pip-licenses to check for compliance
    pip_licenses_base_args = [
        "pip-licenses",
        "--with-system",
        "--ignore-packages",
        "aignostics-foundry-core",
        "--with-authors",
        "--with-maintainer",
        "--with-url",
        "--with-description",
    ]

    # Filter by .license-types-allowed file if it exists
    allowed_licenses = []
    licenses_allow_file = Path(".license-types-allowed")
    if licenses_allow_file.exists():
        allowed_licenses = [
            line.strip()
            for line in licenses_allow_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith(("#", "//"))
        ]
        session.log(f"Found {len(allowed_licenses)} allowed licenses in .license-types-allowed")
    if allowed_licenses:
        allowed_licenses_str = ";".join(allowed_licenses)
        session.log(f"Using --allow-only with: {allowed_licenses_str}")
        pip_licenses_base_args.extend(["--partial-match", "--allow-only", allowed_licenses_str])

    # Generate CSV and JSON reports
    session.run(
        *pip_licenses_base_args,
        "--format=csv",
        "--order=license",
        "--output-file=reports/licenses.csv",
    )
    session.run(
        *pip_licenses_base_args,
        "--with-license-file",
        "--with-notice-file",
        "--format=json",
        "--output-file=" + LICENSES_JSON_PATH,
    )

    # Group by license type
    _format_json_with_jq(session, LICENSES_JSON_PATH)
    licenses_data = json.loads(Path(LICENSES_JSON_PATH).read_text(encoding="utf-8"))
    licenses_grouped: dict[str, list[dict[str, str]]] = {}
    licenses_grouped = {}
    for pkg in licenses_data:
        license_name = pkg["License"]
        package_info = {"Name": pkg["Name"], "Version": pkg["Version"]}
        if license_name not in licenses_grouped:
            licenses_grouped[license_name] = []
        licenses_grouped[license_name].append(package_info)
    Path("reports/licenses_grouped.json").write_text(
        json.dumps(licenses_grouped, indent=2),
        encoding="utf-8",
    )
    _format_json_with_jq(session, "reports/licenses_grouped.json")

    # SBOMs
    session.run("cyclonedx-py", "environment", "-o", SBOM_CYCLONEDX_PATH)
    _format_json_with_jq(session, SBOM_CYCLONEDX_PATH)

    # Generates an SPDX SBOM including vulnerability scanning
    session.run(
        "trivy",
        "fs",
        "uv.lock",
        "--include-dev-deps",
        "--scanners",
        "vuln",
        "--format",
        "spdx",
        "--output",
        SBOM_SPDX_PATH,
        external=True,
    )


def _prepare_coverage(session: nox.Session, posargs: list[str]) -> None:
    """Clean coverage data unless keep-coverage flag is specified.

    Args:
        session: The nox session
        posargs: Command line arguments
    """
    if "--cov-append" not in posargs:
        session.run("rm", "-rf", ".coverage", external=True)


def _sanitize_for_filename(text: str) -> str:
    """Sanitize text for use in filenames by replacing spaces and special chars.

    Args:
        text: Text to sanitize

    Returns:
        Sanitized text suitable for filenames
    """
    return re.sub(r"[\s\(\)]", "-", text).strip("-")


def _extract_custom_marker(posargs: list[str]) -> tuple[str | None, list[str]]:
    """Extract custom marker from pytest arguments.

    Args:
        posargs: Command line arguments

    Returns:
        Tuple of (custom_marker, filtered_posargs)
    """
    custom_marker = None
    new_posargs: list[str] = []
    skip_next = False

    for i, arg in enumerate(posargs):
        if skip_next:
            skip_next = False
            continue

        if arg == "-m" and i + 1 < len(posargs):
            custom_marker = posargs[i + 1]
            skip_next = True
        elif arg != "-m" or i == 0 or posargs[i - 1] != "-m":
            new_posargs.append(arg)

    return custom_marker, new_posargs


def _extract_resolution(posargs: list[str]) -> tuple[str | None, list[str]]:
    """Extract ``--resolution`` from posargs, returning it and the remaining args.

    This allows callers to pass ``--resolution lowest-direct`` alongside other
    pytest arguments without pytest seeing an unknown flag.

    Args:
        posargs: Command line arguments

    Returns:
        Tuple of (resolution, filtered_posargs)
    """
    resolution = None
    new_posargs: list[str] = []
    skip_next = False

    for i, arg in enumerate(posargs):
        if skip_next:
            skip_next = False
            continue

        if arg == "--resolution" and i + 1 < len(posargs):
            resolution = posargs[i + 1]
            skip_next = True
        else:
            new_posargs.append(arg)

    return resolution, new_posargs


def _get_report_type(session: nox.Session, custom_marker: str | None) -> str:
    """Generate report type string based on marker and Python version.

    Args:
        session: The nox session
        custom_marker: Optional pytest marker

    Returns:
        Report type string
    """
    # Create a report type based on marker
    report_type = "regular"
    if custom_marker:
        # Replace spaces and special chars with underscores
        report_type = re.sub(r"[\s\(\)]", "_", custom_marker).strip("_")

    # Add Python version to the report type
    python_version = f"py{str(session.python).replace('.', '')}"

    return f"{python_version}_{report_type}"


def _inject_headline(headline: str, file_name: str) -> None:
    """Inject headline into file.

    - Checks if report file actually exists
    - If so, injects headline
    - If not, does nothing

    Args:
        headline: Headline to inject as first line
        file_name: Name of the report file
    """
    file = Path(file_name)
    if file.is_file():
        header = f"{headline}\n"
        content = file.read_text(encoding=UTF8)
        content = header + content
        file.write_text(content, encoding=UTF8)


def _run_pytest(
    session: nox.Session, test_type: str, custom_marker: str | None, posargs: list[str], report_type: str
) -> None:
    """Run pytest with specified arguments.

    Args:
        session: The nox session
        test_type: Type of test ('sequential' or 'not sequential')
        custom_marker: Optional pytest marker
        posargs: Additional pytest arguments
        report_type: Report type string for output files
    """
    is_sequential = test_type == "sequential"

    # Build base pytest arguments
    sanitized_test_type = _sanitize_for_filename(test_type)
    if custom_marker:
        sanitized_custom_marker = _sanitize_for_filename(custom_marker)
        pytest_args = [
            "pytest",
            "--disable-warnings",
            JUNIT_XML_PREFIX + sanitized_test_type + "_" + sanitized_custom_marker + ".xml",
        ]
    else:
        pytest_args = ["pytest", "--disable-warnings", JUNIT_XML_PREFIX + sanitized_test_type + ".xml"]

    # Distribute tests across available CPUs if not sequential
    if not is_sequential:
        pytest_args.extend(["-n", "logical", "--dist", "worksteal"])

    # Apply the appropriate marker
    marker_value = f"({test_type})"
    if custom_marker:
        marker_value += f" and ({custom_marker})"

    pytest_args.extend(["-m", marker_value])

    # Add additional arguments
    pytest_args.extend(posargs)

    # Report output as markdown for GitHub step summaries
    report_file_name = f"reports/pytest_{report_type}_{'sequential' if is_sequential else 'parallel'}.md"
    pytest_args.extend(["--md-report-output", report_file_name])

    # Remove report file if it exists,
    # as it's only generated for failing tests on the pytest run below
    report_file = Path(report_file_name)
    if report_file.is_file():
        report_file.unlink()

    # Run pytest with the constructed arguments
    session.run(*pytest_args)

    # Inject headline into the report file indicating the report type
    _inject_headline(f"# Failing tests with for test execution with {report_type}\n", report_file_name)


def _generate_coverage_report(session: nox.Session) -> None:
    """Generate coverage report in markdown format.

    Args:
        session: The nox session
    """
    coverage_report_file_name = "reports/coverage.md"
    with Path(coverage_report_file_name).open("w", encoding=UTF8) as outfile:
        session.run("coverage", "report", "--format=markdown", stdout=outfile, stderr=None)
        _inject_headline("# Coverage report", coverage_report_file_name)


def _run_test_suite(session: nox.Session, marker: str = "", cov_append: bool = False) -> None:
    """Run test suite with specified marker.

    Args:
        session: The nox session
        marker: Pytest marker expression
        cov_append: Whether to append to existing coverage data
    """
    posargs = session.posargs[:]
    if "-m" not in posargs and marker:
        posargs.extend(["-m", marker])

    if cov_append:
        posargs.append("--cov-append")

    # Extract --resolution before passing posargs to pytest
    resolution, posargs = _extract_resolution(posargs)

    _setup_venv(session, resolution=resolution)

    # Conditionally clean coverage data
    # Will remove .coverage file if --cov-append is not specified
    _prepare_coverage(session, posargs)

    # Extract custom markers from posargs if present
    custom_marker, filtered_posargs = _extract_custom_marker(posargs)

    # Determine report type from python version and custom marker
    report_type = _get_report_type(session, custom_marker)
    if resolution:
        report_type = f"{report_type}_{resolution.replace('-', '_')}"

    # Run parallel tests
    _run_pytest(session, "not sequential", custom_marker, filtered_posargs, report_type)

    # Run sequential tests
    if "--cov-append" not in filtered_posargs:
        filtered_posargs.extend(["--cov-append"])
    _run_pytest(session, "sequential", custom_marker, filtered_posargs, report_type)

    # Generate coverage report in markdown (only after last test suite)
    # Note: This will be called multiple times, which is fine as it updates the same report
    _generate_coverage_report(session)


@nox.session(python=TEST_PYTHON_VERSIONS, default=False)
def test(session: nox.Session) -> None:
    """Run tests with pytest."""
    _run_test_suite(session)
