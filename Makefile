.PHONY: up down dev-migrate dev-logs test shell migrate deploy logs backup backup-list stop

# --- Development targets (docker-compose.yml) ---

up:
	docker compose up -d

down:
	docker compose down

dev-migrate:
	docker compose run --rm api alembic upgrade head

test:
	docker compose run --rm api pytest tests/ -v

dev-logs:
	docker compose logs -f

shell:
	docker compose run --rm api python -c "from src.db.session import sync_engine; from src.db.models import *; print('OK')"

# --- Production targets (docker-compose.prod.yml) ---

COMPOSE=docker compose -f docker-compose.prod.yml

migrate:
	$(COMPOSE) run --rm migrate

deploy:
	$(COMPOSE) pull || true
	$(COMPOSE) build
	$(COMPOSE) run --rm migrate
	$(COMPOSE) up -d api worker beat caddy

logs:
	$(COMPOSE) logs -f

backup:
	bash scripts/backup.sh

backup-list:
	ls -lh $$(docker volume inspect autodealer-ai-assistant_pg_backups --format '{{ .Mountpoint }}') 2>/dev/null || echo "Run as root or use: docker compose exec postgres ls /backups"

stop:
	$(COMPOSE) down
