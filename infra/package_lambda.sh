#!/usr/bin/env bash
# infra/package_lambda.sh
# --------------------------
# Builds deployment zips for both Lambda functions. Pillow and numpy
# contain compiled extensions, so we fetch manylinux wheels targeted at
# the Lambda execution environment (Python 3.12, x86_64) rather than
# relying on whatever platform this script happens to run on.

source "$(dirname "$0")/config.sh"

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_VERSION="3.12"
LAMBDA_PLATFORM="manylinux2014_x86_64"

package_function() {
    local function_dir="$1"
    local function_name="$2"
    local build_dir="${function_dir}/build"
    local zip_path="${function_dir}/package.zip"

    echo "==> Packaging ${function_name}"
    rm -rf "$build_dir" "$zip_path"
    mkdir -p "$build_dir"

    if [ -s "${function_dir}/requirements.txt" ] && grep -qE '^[A-Za-z]' "${function_dir}/requirements.txt"; then
        pip install \
            --platform "$LAMBDA_PLATFORM" \
            --target "$build_dir" \
            --python-version "$PYTHON_VERSION" \
            --only-binary=:all: \
            -r "${function_dir}/requirements.txt"
    else
        echo "    No third-party dependencies to install for ${function_name}."
    fi

    cp "${function_dir}"/*.py "$build_dir"/

    (cd "$build_dir" && zip -r -q "../package.zip" .)
    echo "    Built ${zip_path}"
}

package_function "${ROOT_DIR}/lambda/process_image" "$LAMBDA_PROCESS_FUNCTION_NAME"
package_function "${ROOT_DIR}/lambda/cleanup_orphans" "$LAMBDA_CLEANUP_FUNCTION_NAME"

echo "==> Packaging complete."
echo "    lambda/process_image/package.zip"
echo "    lambda/cleanup_orphans/package.zip"
