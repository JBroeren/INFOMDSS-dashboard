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

# KNRB Scraper Commands
.PHONY: scraper-install scraper-test scraper-run scraper-seasons scraper-tournaments scraper-matches scraper-persons scraper-klassementen

# Install scraper dependencies
scraper-install:
	pip install -r requirements_scraper.txt

# Test scraper setup
scraper-test:
	python test_scraper.py

# Run complete scraper
scraper-run:
	python knrb_scraper.py

# Run scraper with custom workers
scraper-run-workers:
	python knrb_scraper.py --workers 8

# Run scraper without proxy (with rate limiting)
scraper-run-no-proxy:
	python knrb_scraper.py --no-proxy

# Run specific scraper steps
scraper-seasons:
	python knrb_scraper.py --step seasons

scraper-tournaments:
	python knrb_scraper.py --step tournaments

scraper-matches:
	python knrb_scraper.py --step matches

scraper-persons:
	python knrb_scraper.py --step persons

scraper-klassementen:
	python knrb_scraper.py --step klassementen
