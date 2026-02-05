#!/usr/bin/env bash

if docker ps -a --format '{{.Names}}' | grep -q '^qdrant$'; then
  # Container already exists: just start it (no-op if already running)
  docker start qdrant >/dev/null
else
  # Create and run a new container
  docker run -d \
    --name qdrant \
    -p 6333:6333 \
    -p 6334:6334 \
    qdrant/qdrant
fi
