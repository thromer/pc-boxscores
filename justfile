setup:
    ln -sf ../../scripts/pre-push .git/hooks
    ln -sf ../../scripts/pre-commit .git/hooks

lint files:
    uv run ruff check -q {{files}}
    uv run ruff format --diff {{files}}
    uv run basedpyright {{files}}

lint-root:
    just lint "*.py lib/*.py tests/*.py"

[working-directory: if path_exists('new-games-to-db') == 'true' { 'new-games-to-db' } else { '.' }]
lint-new-games-to-db:
    just lint "*.py tests/*.py"

[working-directory: if path_exists('store-in-gcs') == 'true' { 'store-in-gcs' } else { '.' }]
lint-store-in-gcs:
    just lint "*.py tests/*.py"

check-root:
    just lint-root
    uv run pytest tests/

[working-directory: if path_exists('new-games-to-db') == 'true' { 'new-games-to-db' } else { '.' }]
check-new-games-to-db:
    just lint-new-games-to-db
    uv run pytest tests/

[working-directory: if path_exists('store-in-gcs') == 'true' { 'store-in-gcs' } else { '.' }]
check-store-in-gcs:
    just lint-store-in-gcs
    uv run pytest tests/

lint-all:
    just lint-root
    just lint-new-games-to-db
    just lint-store-in-gcs

check-all:
    just check-root
    just check-new-games-to-db
    just check-store-in-gcs
