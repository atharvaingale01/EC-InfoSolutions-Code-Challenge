.DEFAULT_GOAL := help
COMPOSE     ?= docker compose
COMPOSE_DEV ?= docker compose -f docker-compose.yml -f docker-compose.dev.yml
# Run any target against the dev stack with DEV=1, e.g. `DEV=1 make seed`.
ACTIVE      := $(if $(DEV),$(COMPOSE_DEV),$(COMPOSE))
WEB         := $(ACTIVE) exec web
ENV_PORT     = $$(grep -E '^$(1)=' .env 2>/dev/null | cut -d= -f2)

.PHONY: help env up down build restart logs ps dev dev-down dev-logs migrate makemigrations superuser seed shell dbshell test lint schema fmt clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

env: ## Create .env from .env.example if missing (generates a random DJANGO_SECRET_KEY)
	@test -f .env || ( \
		cp .env.example .env && \
		KEY=$$( (openssl rand -base64 48 2>/dev/null || head -c 48 /dev/urandom | base64) | tr -d '\n=/+' ) && \
		sed -i.bak "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$$KEY|" .env && rm -f .env.bak && \
		echo "Created .env with a generated DJANGO_SECRET_KEY — add your Spotify credentials" )

up: env ## Build and start the full stack (nginx on :80)
	$(COMPOSE) up -d --build
	@P=$(call ENV_PORT,NGINX_PORT); P=$${P:-80}; echo "API: http://localhost:$$P/   Docs: http://localhost:$$P/api/docs/"

down: ## Stop the stack (keeps volumes)
	$(COMPOSE) down

build: ## Rebuild images
	$(COMPOSE) build

restart: ## Restart app containers
	$(COMPOSE) restart web worker beat

logs: ## Tail logs for all services
	$(COMPOSE) logs -f --tail=100

ps: ## Show service status
	$(COMPOSE) ps

dev: env ## Start the dev stack (runserver autoreload, bind-mounted code, no nginx)
	UID=$$(id -u) GID=$$(id -g) $(COMPOSE_DEV) up -d --build
	@P=$(call ENV_PORT,DEV_WEB_PORT); P=$${P:-8000}; echo "Dev API: http://localhost:$$P/   Docs: http://localhost:$$P/api/docs/   (use DEV=1 with other targets)"

dev-down: ## Stop the dev stack
	$(COMPOSE_DEV) down

dev-logs: ## Tail dev stack logs
	$(COMPOSE_DEV) logs -f --tail=100

migrate: ## Apply migrations
	$(WEB) python manage.py migrate

makemigrations: ## Generate migrations
	$(WEB) python manage.py makemigrations

superuser: ## Create a Django superuser
	$(WEB) python manage.py createsuperuser

seed: ## Seed 5 demo users + activity, queue recommendation refresh
	$(WEB) python manage.py seed_demo

shell: ## Django shell
	$(WEB) python manage.py shell

dbshell: ## psql into the database
	$(ACTIVE) exec db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

test: ## Run the test suite inside the web container
	$(ACTIVE) exec -e DJANGO_SETTINGS_MODULE=config.settings.test web pytest

lint: ## Ruff lint + format check + OpenAPI schema validation
	$(WEB) ruff check . && $(WEB) ruff format --check . && $(MAKE) schema

schema: ## Validate the OpenAPI schema (fails on any warning)
	$(ACTIVE) exec -e DJANGO_SETTINGS_MODULE=config.settings.test web python manage.py spectacular --validate --fail-on-warn --file /dev/null

fmt: ## Ruff auto-format
	$(WEB) ruff format .

clean: ## Stop the stack and delete volumes (DESTROYS DATA)
	$(COMPOSE) down -v --remove-orphans
