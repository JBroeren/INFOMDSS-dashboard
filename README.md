# INFOMDSS Dashboard - JSON Importer & Scrapers

This repository contains tools for scraping rowing event data (KNRB and Time Team), importing the scraped JSON into a PostgreSQL database, and a dashboard to visualise the data.

This README focuses on:

- How to run Alembic migrations (required before importing)
- How to build and run the JSON Importer container
- Scraper safety and proxy usage for the scrapers

## Alembic migrations

In order to start, please do the following:
1. copy the .env.example file
2. Rename the copied file to `.env`
3. Add keys or other constants if needed.

#### What does this file do?
This file contains constants that are used to connect to the docker database that is running.

The database schema must be migrated before running the JSON importer so that the correct tables exist. This repository includes an Alembic setup in `json_importer/alembic`. Alembic is a tool which can be used to automatically create database tables and relations between those tables. With migrations you perform actions ("migrations") that alter the tables tructure. It keeps track of those changes allowing you to move back and forth between the migrations. It also means we can easily manage our database columns, tables and relations using python SQLAlchemy.

### Running migrations locally (recommended)

1. Start the docker containers using: `docker compose up -d`
2. Ensure the target Postgres database is reachable and `DB_*` environment variables are set appropriately in the .env file.
3. From the repository root, run (example using the Alembic CLI):

```bash
# Create a venv
python -m venv .venv

# enter the venv
source .venv/bin/activate

# install project requirements in your Python environment, if not already
python -m pip install -r json_importer/requirements.txt

# run alembic migrations
python -m alembic -c json_importer/alembic.ini upgrade head
```

## JSON Importer

The JSON Importer reads JSON files produced by the scrapers and writes them into the relational database. The importer supports `knrb`sources.

### Build the Docker image

Run from the repository root:

```bash
docker build -t infomdss/json-importer -f json_importer/Dockerfile ./json_importer
```

### Run the container

Example (replace values as needed):

```bash
docker run --rm \
	-e DB_HOST=<your_db_host> \
	-e DB_NAME=<your_db_name> \
	-e DB_USER=<your_db_user> \
	-e DB_PASSWORD=<your_db_password> \
	-e DB_PORT=5432 \
	-e KNRB_DATA_DIR=/data/knrb_data \
	-e TIME_TEAM_DATA_DIR=/data/time_team_data \
	-v $(pwd)/data:/data \
	infomdss/json-importer
```

- The importer accepts `--source knrb|time_team|all` to select which JSON source(s) to import.
- If you use a docker-compose setup you can mount `./data` into the container and pass the same environment variables.

### Environment variables used by the importer

- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` – PostgreSQL connection
- `KNRB_DATA_DIR` – path inside the container to KNRB JSON files (default `/data/knrb_data`)
- `TIME_TEAM_DATA_DIR` – path inside the container to Time Team JSON files (default `/data/time_team_data`)

## Scrapers and proxy safety

The scrapers in this repository fetch data from external endpoints. Running them without rotating proxies or proxy URLs may cause your IP address to be blocked by the target servers. It is not recommended to run these scrapers without knowing how to setup a proxy rotation service and connecting it to these scripts.

## Quick checklist before importing

1. Start or ensure PostgreSQL is running and reachable.
2. Run Alembic migrations (`alembic upgrade head`) so required tables exist.
3. Ensure `data/knrb_data` and/or `data/time_team_data` contain the JSON files.
4. Build/run the JSON Importer container with proper `DB_*` env vars and mounted `data/` volume.