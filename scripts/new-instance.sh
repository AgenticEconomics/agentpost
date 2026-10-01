#!/bin/bash
# Create a new AgentPost instance with its own name, ports, and domain.
#
# Usage:
#   ./scripts/new-instance.sh <instance-name> [api-port] [web-port]
#
# Example:
#   ./scripts/new-instance.sh xingu 8765 58080
#   ./scripts/new-instance.sh jarvik 18765 58081
#
# After creation:
#   cd <instance-name> && docker compose up -d

set -euo pipefail

NAME="${1:?Usage: new-instance.sh <instance-name> [api-port] [web-port]}"
API_PORT="${2:-8765}"
WEB_PORT="${3:-58080}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
INSTANCE_DIR="$NAME"

if [ -d "$INSTANCE_DIR" ]; then
    echo "Error: directory '$INSTANCE_DIR' already exists." >&2
    exit 1
fi

mkdir -p "$INSTANCE_DIR"

# Generate .env
cat > "$INSTANCE_DIR/.env" <<EOF
# AgentPost instance: $NAME
# Created: $(date -u +%Y-%m-%dT%H:%M:%SZ)

INSTANCE_NAME=$NAME
AGENTPOST_DOMAIN=${NAME}.local
AGENTPOST_OPERATOR_TOKEN=$(openssl rand -hex 32)
API_PORT=$API_PORT
WEB_PORT=$WEB_PORT
IMAGE_REGISTRY=ghcr.io/AgenticEconomics
IMAGE_TAG=0.1.0
EOF

# Copy pull-only compose file
cp "$REPO_DIR/docker-compose.pull.yml" "$INSTANCE_DIR/docker-compose.yml"

echo ""
echo "Instance '$NAME' created in ./$INSTANCE_DIR/"
echo ""
echo "  API:       http://localhost:$API_PORT"
echo "  Console:   http://localhost:$WEB_PORT"
echo "  Domain:    ${NAME}.local"
echo "  Operator:  $(grep AGENTPOST_OPERATOR_TOKEN "$INSTANCE_DIR/.env" | cut -d= -f2)"
echo ""
echo "  Start:     cd $INSTANCE_DIR && docker compose up -d"
echo "  Register:  docker compose exec -e AGENTPOST_TOKEN=<token> api agentpost register --id alice --name Alice"
echo ""
