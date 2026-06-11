#!/bin/bash
# Reassemble the pre-built frontend from split parts
# Run this in /opt/drboz
set -e
cd "$(dirname "$0")/.."
echo "Reassembling frontend build..."
cat frontend-build-parts/frontend-build-part-* | tar xzf -
echo "Done. Now run:"
echo "  docker cp frontend-build/. open-webui:/app/build/"
echo "  docker restart open-webui"
