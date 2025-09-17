# Docker Compose Commands
.PHONY: build up down restart logs clean

# create venv
venv:
	python -m venv .venv
	chmod +x .venv/bin/activate
	.venv/bin/activate
	pip install -r dashboard/requirements.txt

# Build all services
build:
	docker-compose build

# Start all services
up:
	docker-compose up -d

# Stop all services
down:
	docker-compose down

# Restart all services
restart: down up

# View logs for all services
logs:
	docker-compose logs -f

# View logs for specific service (usage: make logs-service SERVICE=flask-app)
logs-service:
	docker-compose logs -f $(SERVICE)

# Clean up containers, networks, and volumes
clean:
	docker-compose down -v --remove-orphans
	docker system prune -f

# Start specific service (usage: make start-service SERVICE=flask-app)
start-service:
	docker-compose up -d $(SERVICE)

# Stop specific service (usage: make stop-service SERVICE=flask-app)
stop-service:
	docker-compose stop $(SERVICE)

# Show status of all services
status:
	docker-compose ps

# Execute shell in flask-app container
shell-flask:
	docker-compose exec flask-app /bin/bash

# Execute shell in jupyter container
shell-jupyter:
	docker-compose exec jupyter /bin/bash

# Execute shell in database container
shell-db:
	docker-compose exec db_dashboard psql -U student -d dashboard

# Scraper Commands
.PHONY: scrape-knrb scrape-time-team scrape-all import-all import-knrb import-time-team create-tables migrate status clean-data

# Run KNRB scraper (usage: make scrape-knrb WORKERS=16)
scrape-knrb:
	MAX_WORKERS=$(or $(WORKERS),10) docker compose --profile scraper run --rm knrb-scraper

# Run Time Team scraper (usage: make scrape-time-team WORKERS=16)
scrape-time-team:
	MAX_WORKERS=$(or $(WORKERS),10) docker compose --profile scraper run --rm time-team-scraper

# Run both scrapers (usage: make scrape-all WORKERS=16)
scrape-all: scrape-knrb scrape-time-team

# Import all JSON data to database
import-all:
	docker compose --profile importer run --rm json-importer python json_importer.py --source all

# Import only KNRB data
import-knrb:
	docker compose --profile importer run --rm json-importer python json_importer.py --source knrb

# Import only Time Team data
import-time-team:
	docker compose --profile importer run --rm json-importer python json_importer.py --source time_team

# Create database tables
create-tables:
	docker compose --profile importer run --rm json-importer python json_importer.py --create-tables --source all

# Run database migrations
migrate:
	docker compose --profile importer run --rm json-importer alembic upgrade head

# Show data status
status:
	@echo "=== JSON Data Status ==="
	@if [ -d "data/knrb_data" ]; then \
		echo "KNRB Data:"; \
		find data/knrb_data -name "*.json" | wc -l | xargs echo "  Total JSON files:"; \
		echo "  Seasons: $$(find data/knrb_data/seasons -name "*.json" 2>/dev/null | wc -l)"; \
		echo "  Tournaments: $$(find data/knrb_data/tournaments -name "*.json" 2>/dev/null | wc -l)"; \
		echo "  Matches: $$(find data/knrb_data/matches -name "*.json" 2>/dev/null | wc -l)"; \
		echo "  Races: $$(find data/knrb_data/races -name "*.json" 2>/dev/null | wc -l)"; \
		echo "  Persons: $$(find data/knrb_data/persons -name "*.json" 2>/dev/null | wc -l)"; \
	else \
		echo "KNRB Data: Not found"; \
	fi
	@echo ""
	@if [ -d "data/time_team_data" ]; then \
		echo "Time Team Data:"; \
		find data/time_team_data -name "*.json" | wc -l | xargs echo "  Total JSON files:"; \
		echo "  Regattas: $$(find data/time_team_data/regattas -name "*.json" 2>/dev/null | wc -l)"; \
		echo "  Events: $$(find data/time_team_data/events -name "*.json" 2>/dev/null | wc -l)"; \
		echo "  Races: $$(find data/time_team_data/races -name "*.json" 2>/dev/null | wc -l)"; \
		echo "  Entries: $$(find data/time_team_data/entries -name "*.json" 2>/dev/null | wc -l)"; \
		echo "  Clubs: $$(find data/time_team_data/clubs -name "*.json" 2>/dev/null | wc -l)"; \
		echo "  Members: $$(find data/time_team_data/members -name "*.json" 2>/dev/null | wc -l)"; \
	else \
		echo "Time Team Data: Not found"; \
	fi
	@echo ""
	@echo "=== Database Status ==="
	@docker compose --profile importer run --rm json-importer python -c "from json_importer import JSONImporter; importer = JSONImporter(); summary = importer.get_import_summary(); [print(f'  {table}: {count:,} records') for table, count in summary.items()]"

# Clean JSON data directories (interactive)
clean-data:
	@echo "This will remove all JSON data. Are you sure? (y/N)"; \
	read response; \
	if [ "$$response" = "y" ] || [ "$$response" = "Y" ]; then \
		rm -rf data/knrb_data/* data/time_team_data/*; \
		echo "Data directories cleaned"; \
	else \
		echo "Operation cancelled"; \
	fi
