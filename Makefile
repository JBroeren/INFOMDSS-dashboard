# Docker Compose Commands
.PHONY: build up down restart logs clean

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
