#!/usr/bin/env bash
set -euo pipefail

ERRORS=0

# Check for Python backend imports in TS source
if grep -rq "python\|pydantic\|uvicorn\|aithru_agent\." src/ tests/ examples/ 2>/dev/null; then
  echo "FAIL: TypeScript code references Python backend"
  grep -rn "python\|pydantic\|uvicorn\|aithru_agent\." src/ tests/ examples/ 2>/dev/null || true
  ERRORS=$((ERRORS + 1))
fi

# Check for Python shebangs or shell calls to python
if grep -rq "#!/usr/bin/env python\|uv run\|python3\|python " src/ tests/ examples/ scripts/ --exclude=check-no-python.sh 2>/dev/null; then
  echo "FAIL: TypeScript code may start a Python process"
  grep -rn "#!/usr/bin/env python\|uv run\|python3\b" src/ tests/ examples/ scripts/ --exclude=check-no-python.sh 2>/dev/null || true
  ERRORS=$((ERRORS + 1))
fi

# Check package.json for Python dependencies
if grep -q "pydantic\|fastapi\|uvicorn" package.json 2>/dev/null; then
  echo "FAIL: package.json references Python dependencies"
  ERRORS=$((ERRORS + 1))
fi

if [ "$ERRORS" -gt 0 ]; then
  echo ""
  echo "check:no-python-backend FAILED with $ERRORS violation(s)"
  exit 1
fi

echo "check:no-python-backend PASSED"
