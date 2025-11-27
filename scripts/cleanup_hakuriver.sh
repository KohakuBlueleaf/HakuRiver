#!/bin/bash
# Cleanup script for old HakuRiver containers and images
# Run this on each node to clean up after migration to KohakuRiver

set -e

echo "=== HakuRiver Cleanup Script ==="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if docker is available
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed or not in PATH"
    exit 1
fi

# Dry run mode
DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
    DRY_RUN=true
    print_warn "Running in DRY RUN mode - no changes will be made"
    echo ""
fi

# 1. Stop and remove hakuriver-vps-* containers
echo "=== Step 1: Cleaning up hakuriver-vps-* containers ==="
VPS_CONTAINERS=$(docker ps -a --filter "name=hakuriver-vps-" --format "{{.Names}}" 2>/dev/null || true)
if [ -n "$VPS_CONTAINERS" ]; then
    echo "Found VPS containers:"
    echo "$VPS_CONTAINERS"
    if [ "$DRY_RUN" = false ]; then
        for container in $VPS_CONTAINERS; do
            print_info "Stopping and removing: $container"
            docker stop "$container" 2>/dev/null || true
            docker rm -f "$container" 2>/dev/null || true
        done
    fi
else
    print_info "No hakuriver-vps-* containers found"
fi
echo ""

# 2. Stop and remove hakuriver-task-* containers
echo "=== Step 2: Cleaning up hakuriver-task-* containers ==="
TASK_CONTAINERS=$(docker ps -a --filter "name=hakuriver-task-" --format "{{.Names}}" 2>/dev/null || true)
if [ -n "$TASK_CONTAINERS" ]; then
    echo "Found task containers:"
    echo "$TASK_CONTAINERS"
    if [ "$DRY_RUN" = false ]; then
        for container in $TASK_CONTAINERS; do
            print_info "Stopping and removing: $container"
            docker stop "$container" 2>/dev/null || true
            docker rm -f "$container" 2>/dev/null || true
        done
    fi
else
    print_info "No hakuriver-task-* containers found"
fi
echo ""

# 3. Stop and remove hakuriver-env-* containers (host-side managed containers)
echo "=== Step 3: Cleaning up hakuriver-env-* containers ==="
ENV_CONTAINERS=$(docker ps -a --filter "name=hakuriver-env-" --format "{{.Names}}" 2>/dev/null || true)
if [ -n "$ENV_CONTAINERS" ]; then
    echo "Found environment containers:"
    echo "$ENV_CONTAINERS"
    if [ "$DRY_RUN" = false ]; then
        for container in $ENV_CONTAINERS; do
            print_info "Stopping and removing: $container"
            docker stop "$container" 2>/dev/null || true
            docker rm -f "$container" 2>/dev/null || true
        done
    fi
else
    print_info "No hakuriver-env-* containers found"
fi
echo ""

# 4. Remove hakuriver/* images
echo "=== Step 4: Cleaning up hakuriver/* images ==="
HAKURIVER_IMAGES=$(docker images --format "{{.Repository}}:{{.Tag}}" | grep "^hakuriver/" 2>/dev/null || true)
if [ -n "$HAKURIVER_IMAGES" ]; then
    echo "Found hakuriver images:"
    echo "$HAKURIVER_IMAGES"
    if [ "$DRY_RUN" = false ]; then
        for image in $HAKURIVER_IMAGES; do
            print_info "Removing image: $image"
            docker rmi -f "$image" 2>/dev/null || true
        done
    fi
else
    print_info "No hakuriver/* images found"
fi
echo ""

# 5. Summary
echo "=== Cleanup Summary ==="
if [ "$DRY_RUN" = true ]; then
    print_warn "DRY RUN completed - no changes were made"
    print_info "Run without --dry-run to actually perform cleanup"
else
    print_info "Cleanup completed!"
fi

echo ""
echo "=== Remaining Docker Resources ==="
echo "Containers:"
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Image}}" | head -20
echo ""
echo "Images (kohakuriver/*):"
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | grep -E "^(REPOSITORY|kohakuriver)" || echo "  (none)"
