#!/bin/bash
# Run super-linter locally using Docker
# Reads environment variables from .github/workflows/release.yml and filters out GITHUB_TOKEN
# Additional local env vars can be defined in scripts/.env

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKFLOW_FILE="${REPO_ROOT}/.github/workflows/release.yml"
LOCAL_ENV_FILE="${SCRIPT_DIR}/local.env"

# Super-linter image - extract version from workflow file
SUPER_LINTER_VERSION=v8
SUPER_LINTER_IMAGE="ghcr.io/super-linter/super-linter:${SUPER_LINTER_VERSION}"

# Extract env vars from the Lint step in release.yml
# - Find the "name: Lint" step and extract the env block
# - Filter out GITHUB_TOKEN and any ${{ }} expressions
extract_env_vars() {
	local in_lint_step=false
	local in_env_block=false
	local env_vars=()

	while IFS= read -r line; do
		# Detect start of Lint step
		if [[ "$line" =~ ^[[:space:]]*-[[:space:]]*name:[[:space:]]*Lint ]]; then
			in_lint_step=true
			continue
		fi

		# Detect start of next step (ends Lint step)
		if [[ "$in_lint_step" == true && "$line" =~ ^[[:space:]]*-[[:space:]]*name: ]]; then
			break
		fi

		# Detect env block within Lint step
		if [[ "$in_lint_step" == true && "$line" =~ ^[[:space:]]*env: ]]; then
			in_env_block=true
			continue
		fi

		# Detect end of env block (line with less indentation or new key)
		if [[ "$in_env_block" == true && "$line" =~ ^[[:space:]]*[^[:space:]] && ! "$line" =~ ^[[:space:]]{10,} ]]; then
			if [[ ! "$line" =~ ^[[:space:]]+[A-Z_]+: ]]; then
				in_env_block=false
			fi
		fi

		# Extract env var if in env block
		if [[ "$in_env_block" == true && "$line" =~ ^[[:space:]]+([A-Z_]+):[[:space:]]*(.+)$ ]]; then
			local key="${BASH_REMATCH[1]}"
			local value="${BASH_REMATCH[2]}"

			# Skip GITHUB_TOKEN and any ${{ }} expressions
			if [[ "$key" == "GITHUB_TOKEN" ]]; then
				continue
			fi
			if [[ "$value" =~ \$\{\{ ]]; then
				continue
			fi

			env_vars+=("-e" "${key}=${value}")
		fi
	done <"${WORKFLOW_FILE}"

	printf '%s\n' "${env_vars[@]}"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
	case $1 in
	--help | -h)
		echo "Usage: $0 [OPTIONS]"
		echo ""
		echo "Options:"
		echo "  --help    Show this help message"
		echo ""
		echo "Environment variables are read from:"
		echo "  1. ${WORKFLOW_FILE} (Lint step)"
		echo "  2. ${LOCAL_ENV_FILE} (optional, for local overrides)"
		exit 0
		;;
	*)
		echo "Unknown option: $1"
		exit 1
		;;
	esac
done

# Build environment variables array
ENV_VARS=("-e" "RUN_LOCAL=true")

# Read env vars from workflow file
while IFS= read -r var; do
	[[ -n "$var" ]] && ENV_VARS+=("$var")
done < <(extract_env_vars)

# Read additional env vars from local .env file if it exists
if [[ -f "${LOCAL_ENV_FILE}" ]]; then
	echo "📄 Loading local env vars from ${LOCAL_ENV_FILE}"
	while IFS= read -r line || [[ -n "$line" ]]; do
		# Skip comments and empty lines
		[[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
		# Extract KEY=VALUE
		if [[ "$line" =~ ^([A-Z_]+)=(.*)$ ]]; then
			ENV_VARS+=("-e" "${BASH_REMATCH[1]}=${BASH_REMATCH[2]}")
		fi
	done <"${LOCAL_ENV_FILE}"
fi

echo "🚀 Running super-linter on ${REPO_ROOT}"
echo "📦 Image: ${SUPER_LINTER_IMAGE}"
echo "📋 Environment variables:"
for ((i = 0; i < ${#ENV_VARS[@]}; i += 2)); do
	echo "   ${ENV_VARS[i + 1]}"
done
echo ""

docker run --rm \
	"${ENV_VARS[@]}" \
	-v "${REPO_ROOT}:/tmp/lint" \
	"${SUPER_LINTER_IMAGE}"
