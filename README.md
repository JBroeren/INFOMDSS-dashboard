# INFOMDSS Dashboard

KNRB data management system with scraping, migration, and visualization.

## Quick Start

```bash
# Start services
make up

# Access dashboard
open http://localhost:8080
```

## Services

| Service | Port | URL | Purpose |
|---------|------|-----|---------|
| Dashboard | 8080 | http://localhost:8080 | Main app |
| MongoDB Admin | 8082 | http://localhost:8082 | DB management |
| PostgreSQL Admin | 8081 | http://localhost:8081 | DB management |

## Commands

```bash
# Service management
make up/down/restart/status/logs/clean

# Run scraper (full data collection)
docker-compose --profile scraper run --rm knrb-scraper python knrb_scraper.py --workers 8

# Run migration (PostgreSQL → MongoDB)
docker-compose --profile migration up migration
```

## Scraper Options

```bash
# Full scrape
docker-compose --profile scraper run --rm knrb-scraper python knrb_scraper.py --workers 8

# Tournament-specific
docker-compose --profile scraper run --rm knrb-scraper python knrb_scraper.py --tournament-mode --tournament-name "2024"

# Without proxy (rate limited)
docker-compose --profile scraper run --rm knrb-scraper python knrb_scraper.py --no-proxy
```

## Troubleshooting

```bash
# Check service status
make status

# View logs
make logs

# Clean restart
make clean && make up
```

For detailed scraper documentation, see `scraper/README.md`.
