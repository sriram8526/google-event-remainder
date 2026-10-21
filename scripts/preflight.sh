#!/usr/bin/env bash
# Pre-submission gates: code health, secrets, repository size, single branch.
# Run from the repository root after committing: bash scripts/preflight.sh
set -uo pipefail

MAX_REPO_KB=10240
fail=0
pass() { printf 'PASS  %s\n' "$1"; }
bad()  { printf 'FAIL  %s\n' "$1"; fail=1; }

echo "== 1. Static analysis and tests"
ruff check . >/dev/null && ruff format --check . >/dev/null && mypy app >/dev/null \
  && bandit -q -r app >/dev/null && python -m pytest -q >/dev/null \
  && pass "ruff, format, mypy, bandit, pytest" || bad "static analysis or tests failed (run each tool for details)"

echo "== 2. Secrets"
pattern='AIza[0-9A-Za-z_-]{35}|sk-[A-Za-z0-9_-]{20,}'
if git grep -InE "$pattern" -- . ':!scripts/preflight.sh' ':!tests' >/dev/null; then
  bad "key-like string found in tracked files"
else pass "no key-like strings in tracked files"; fi
if [ -n "$(git log --all --oneline -G"$pattern" -- . ':!scripts/preflight.sh' ':!tests' 2>/dev/null)" ]; then
  bad "key-like string found in git history"
else pass "no key-like strings in git history"; fi
if git ls-files | grep -E '^\.env(\.|$)' | grep -vq '^\.env\.example$'; then
  bad ".env file is tracked"
else pass "no .env file tracked"; fi

echo "== 3. Repository size (limit ${MAX_REPO_KB} KB including .git)"
git gc --quiet 2>/dev/null
git_kb=$(du -sk .git | cut -f1)
tracked_kb=$(git ls-files -z | xargs -0 du -ck 2>/dev/null | tail -1 | cut -f1)
size_kb=$((git_kb + tracked_kb))   # ignored folders (caches, .venv) are not part of the repository
if [ "$size_kb" -lt "$MAX_REPO_KB" ]; then
  pass "repository is ${size_kb} KB (.git ${git_kb} KB + tracked files ${tracked_kb} KB)"
else bad "repository is ${size_kb} KB"; fi

echo "== 4. Single branch"
locals=$(git branch --format='%(refname:short)' | wc -l | tr -d ' ')
remotes=$(git branch -r 2>/dev/null | grep -vc -- '->' || true)
if [ "$locals" -eq 1 ] && [ "$remotes" -le 1 ]; then
  pass "one local branch ($(git branch --show-current)) and ${remotes} remote branch(es)"
else bad "found ${locals} local and ${remotes} remote branches"; fi

echo "== 5. Working tree"
if [ -z "$(git status --porcelain)" ]; then pass "everything is committed"; else bad "uncommitted changes"; fi

echo
if [ "$fail" -eq 0 ]; then echo "All gates passed."; else echo "Fix the failures above before submitting."; fi
exit "$fail"
