"""Downloaded SBCs are kept, and kept local (ADR 0016).

Checked on the source itself, so a change that would delete an issuer's PDF,
or let one reach the public repository, fails here before it can run.
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_DELETES = re.compile(r"\.unlink\(|os\.remove\(|os\.unlink\(|shutil\.rmtree\(|\.rmdir\(")


def test_no_sbc_ingestion_code_deletes_a_file():
    offenders = [
        f"{path.relative_to(ROOT)}:{number}"
        for path in sorted((ROOT / "src/ingestion/sbc").glob("*.py"))
        for number, line in enumerate(path.read_text().splitlines(), 1)
        if _DELETES.search(line)
    ]

    assert offenders == []


def test_the_data_directory_stays_ignored_by_git():
    assert "data/" in (ROOT / ".gitignore").read_text().splitlines()


def test_no_pdf_is_tracked_by_git():
    tracked = subprocess.run(["git", "ls-files", "*.pdf"], cwd=ROOT, capture_output=True, text=True, check=True)

    assert tracked.stdout == ""
