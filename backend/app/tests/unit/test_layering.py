"""Architecture guard: the intelligence layer must never touch the database."""

import subprocess
import sys

from app.config import BACKEND_DIR

MODULES = ["extraction", "classification", "prioritization", "missing_fields", "response", "drafting", "numbers",
           "text", "models", "config_loader"]


def test_intelligence_imports_no_sqlalchemy_or_gnani():
    code = (
        "import sys\n"
        + "".join(f"import app.intelligence.{m}\n" for m in MODULES)
        + "bad = sorted(m for m in sys.modules if m.split('.')[0] == 'sqlalchemy' or m.startswith(('app.models',"
          " 'app.database', 'app.gnani', 'app.services', 'app.workflows')))\n"
        + "print(','.join(bad))\n"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=BACKEND_DIR, capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "", f"intelligence layer imported: {result.stdout.strip()}"
