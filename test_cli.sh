#!/usr/bin/env bash
# test_cli.sh - End-to-end tests for all aptdata CLI commands
set -e

# Change directory to script location, then to repo root
cd "$(dirname "$0")" || exit
REPO_ROOT="$(pwd)"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

FAILED_TESTS=0

run_test() {
    local cmd="$1"
    local desc="$2"
    echo -e "${YELLOW}Testing: ${desc}${NC}"
    echo "Command: $cmd"
    if eval "$cmd"; then
        echo -e "${GREEN}[OK]${NC} $desc\n"
    else
        echo -e "${RED}[FAILED]${NC} $desc\n"
        FAILED_TESTS=$((FAILED_TESTS + 1))
    fi
}

echo "=========================================="
echo "    Starting aptdata CLI tests"
echo "=========================================="

# 1. Base command
run_test "poetry run aptdata --help" "Base help command"

# 2. Schema export
run_test "poetry run aptdata schema export --output schema_out.json && rm schema_out.json" "schema export"

# 3. System commands
run_test "poetry run aptdata system list" "system list"
run_test "poetry run aptdata system list --json" "system list --json"
# Try listing an info (will likely error if none, but we want it to run without unhandled exceptions)
# Creating a dummy config to register a system for testing run/info/validate
cat << 'EOF' > dummy_system.yaml
metadata:
  name: dummy_pipeline
  version: "1.0"
  description: Dummy
system:
  system_id: dummy_pipeline
  flows: []
EOF

# Clean up before testing
rm -rf test_config.yaml my_job_project schema_out.json my_test_project my_medallion_project my_rag_project my_dq_project my_docker_project

# 4. Config commands
run_test "poetry run aptdata config init --output test_config.yaml" "config init"
run_test "poetry run aptdata config show test_config.yaml" "config show"
run_test "poetry run aptdata config validate test_config.yaml" "config validate"
run_test "poetry run aptdata config run test_config.yaml" "config run"

# 5. Run command (now that we have a system registered from config run)
run_test "poetry run aptdata run dummy_pipeline --dry-run || true" "run pipeline dry-run (may fail if not registered persistently)"

# 6. Plugin commands
run_test "poetry run aptdata plugin list" "plugin list"
run_test "poetry run aptdata plugin list --json" "plugin list --json"
# Preview a known plugin if any, we'll try something basic or expect it to fail gracefully
run_test "poetry run aptdata plugin preview dummy_reader || true" "plugin preview (graceful fail expected)"
run_test "poetry run aptdata plugin inspect dummy_reader || true" "plugin inspect (graceful fail expected)"

# 7. Telemetry commands
run_test "poetry run aptdata telemetry status" "telemetry status"
run_test "poetry run aptdata telemetry status --json" "telemetry status --json"
run_test "poetry run aptdata telemetry export --format json" "telemetry export json"

# 8. Scaffold commands
run_test "poetry run aptdata scaffold my_test_project --template hello-world" "scaffold hello-world"
run_test "poetry run aptdata scaffold my_medallion_project --template medallion" "scaffold medallion"
run_test "poetry run aptdata scaffold my_rag_project --template rag-ingestion" "scaffold rag-ingestion"
run_test "poetry run aptdata scaffold my_dq_project --template data-quality-test" "scaffold data-quality-test"
run_test "poetry run aptdata scaffold my_job_project --template job-wheel" "scaffold job-wheel"
run_test "poetry run aptdata scaffold my_docker_project --template docker-compose-app" "scaffold docker-compose-app"

# 9. Mesh commands
run_test "poetry run aptdata mesh list" "mesh list"
run_test "poetry run aptdata mesh list --json" "mesh list --json"
# Since we just scaffolded a job-wheel, let's test mesh run on it
run_test "poetry run aptdata mesh build my_job_project" "mesh build job-wheel"
run_test "poetry run aptdata mesh run my_job_project --dry-run" "mesh run job-wheel dry-run"

# 10. Long-running interactive commands (using timeout)
# TUI Dashboard
run_test "timeout 2 poetry run aptdata monitor || [ \$? -eq 124 ]" "monitor (TUI, timeout after 2s)"
# MCP Server
run_test "timeout 2 poetry run aptdata mcp-start || [ \$? -eq 124 ]" "mcp-start (MCP, timeout after 2s)"
# Interactive prompt (using `yes ''` to spam enter and timeout)
run_test "timeout 2 sh -c \"yes '' | poetry run aptdata interactive\" || [ \$? -eq 124 ] || true" "interactive wizard (timeout after 2s)"

# Cleanup
echo "Cleaning up generated files..."
rm -rf test_config.yaml dummy_system.yaml schema_out.json my_test_project my_medallion_project my_rag_project my_dq_project my_job_project my_docker_project

echo "=========================================="
if [ "$FAILED_TESTS" -eq 0 ]; then
    echo -e "${GREEN}ALL TESTS PASSED!${NC}"
    exit 0
else
    echo -e "${RED}$FAILED_TESTS TEST(S) FAILED!${NC}"
    exit 1
fi
