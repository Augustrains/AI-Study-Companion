#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATABASE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CONTAINER_NAME="adaptive-db-integration-$$"

cleanup() {
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker run --detach --rm \
  --name "$CONTAINER_NAME" \
  --env POSTGRES_PASSWORD=integration \
  --env POSTGRES_DB=adaptive_integration \
  --volume "$DATABASE_ROOT:/work:ro" \
  postgres:16-alpine >/dev/null

for _ in $(seq 1 30); do
  if docker exec "$CONTAINER_NAME" pg_isready --username postgres --dbname adaptive_integration >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

docker exec "$CONTAINER_NAME" pg_isready --username postgres --dbname adaptive_integration >/dev/null

for sql_file in \
  /work/backend/migrations/001_content_learning.sql \
  /work/backend/migrations/002_assessment_and_practice.sql \
  /work/backend/migrations/003_content_governance.sql \
  /work/backend/migrations/004_runtime_hardening.sql \
  /work/backend/generated/curriculum_seed.sql \
  /work/backend/generated/knowledge_mapping_seed.sql \
  /work/backend/generated/practice_mapping_seed.sql \
  /work/backend/migrations/005_runtime_roles.sql \
  /work/backend/migrations/006_localization_and_explanations.sql \
  /work/backend/generated/localization_seed.sql \
  /work/backend/migrations/007_localization_roles.sql \
  /work/backend/migrations/008_algorithm_and_mastery.sql \
  /work/backend/migrations/009_algorithm_roles.sql \
  /work/backend/tests/postgres_integration_assertions.sql
do
  docker exec "$CONTAINER_NAME" psql \
    --quiet \
    --username postgres \
    --dbname adaptive_integration \
    --set ON_ERROR_STOP=1 \
    --file "$sql_file"
done
