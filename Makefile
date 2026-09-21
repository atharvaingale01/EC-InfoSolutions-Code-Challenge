.DEFAULT_GOAL := help
COMPOSE ?= docker compose
WEB     := $(COMPOSE) exec web

.PHONY: help env up down build restart logs ps migrate makemigrations superuser seed shell dbshell test lint fmt clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

env: ## Create .env from .env.example if missing
	@test -f .env || (cp .env.example .env && echo "Created .env — add your Spotify credentials")

up: env ## Build and start the full stack (nginx on :80)
	$(COMPOSE) up -d --build
	@echo "API: http://localhost:$${NGINX_PORT:-80}/   Docs: http://localhost:$${NGINX_PORT:-80}/api/docs/"

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
	$(WEB) python manage.py dbshell

test: ## Run the test suite inside the web container
	$(COMPOSE) exec -e DJANGO_SETTINGS_MODULE=config.settings.test web pytest

lint: ## Ruff lint + format check
	$(WEB) ruff check . && $(WEB) ruff format --check .

fmt: ## Ruff auto-format
	$(WEB) ruff format .

clean: ## Stop the stack and delete volumes (DESTROYS DATA)
	$(COMPOSE) down -v --remove-orphans
