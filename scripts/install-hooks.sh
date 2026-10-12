#!/bin/sh
# Install the pre-push gate. Hooks live outside version control, so this script is
# the versioned part -- run it once per clone.
set -e
cd "$(dirname "$0")/.."
mkdir -p .git/hooks
cat > .git/hooks/pre-push <<'HOOK'
#!/bin/sh
# Blueprint 7.2 requires tests before merge. Until GitHub Actions can run (pushing
# .github/workflows/ needs a token with `workflow` scope), this hook is the gate.
exec ./scripts/check.sh
HOOK
chmod +x .git/hooks/pre-push
echo "installed .git/hooks/pre-push -> scripts/check.sh"
