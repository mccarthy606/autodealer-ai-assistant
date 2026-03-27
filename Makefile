.PHONY: up down migrate test logs shell

up:
	docker compose up -d

down:
	docker compose down

migrate:
	docker compose run --rm api alembic upgrade head

test:
	docker compose run --rm api pytest tests/ -v

logs:
	docker compose logs -f

shell:
	docker compose run --rm api python -c "from src.db.session import sync_engine; from src.db.models import *; print('OK')"
