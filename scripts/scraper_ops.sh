#!/bin/bash
# Scraper Operations Script
# Helper script for common scraper and importer operations

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  scrape-knrb [workers]     Run KNRB scraper (default: 8 workers)"
    echo "  scrape-time-team [workers] Run Time Team scraper (default: 8 workers)"
    echo "  scrape-all [workers]      Run both scrapers (default: 8 workers)"
    echo "  import-all               Import all JSON data to database"
    echo "  import-knrb              Import only KNRB data"
    echo "  import-time-team         Import only Time Team data"
    echo "  create-tables            Create database tables"
    echo "  migrate                  Run database migrations"
    echo "  status                   Show data status"
    echo "  clean-data               Clean JSON data directories"
    echo "  help                     Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 scrape-knrb 16        # Run KNRB scraper with 16 workers"
    echo "  $0 scrape-all 4          # Run both scrapers with 4 workers"
    echo "  $0 import-all            # Import all data to database"
}

# Function to run KNRB scraper
scrape_knrb() {
    local workers=${1:-8}
    print_status "Running KNRB scraper with $workers workers..."
    MAX_WORKERS=$workers docker compose --profile scraper run --rm knrb-scraper
    print_success "KNRB scraper completed"
}

# Function to run Time Team scraper
scrape_time_team() {
    local workers=${1:-8}
    print_status "Running Time Team scraper with $workers workers..."
    MAX_WORKERS=$workers docker compose --profile scraper run --rm time-team-scraper
    print_success "Time Team scraper completed"
}

# Function to run both scrapers
scrape_all() {
    local workers=${1:-8}
    print_status "Running all scrapers with $workers workers..."
    scrape_knrb $workers
    scrape_time_team $workers
    print_success "All scrapers completed"
}

# Function to import all data
import_all() {
    print_status "Importing all JSON data to database..."
    docker compose --profile importer run --rm json-importer python json_importer.py --source all
    print_success "All data imported successfully"
}

# Function to import KNRB data only
import_knrb() {
    print_status "Importing KNRB data to database..."
    docker compose --profile importer run --rm json-importer python json_importer.py --source knrb
    print_success "KNRB data imported successfully"
}

# Function to import Time Team data only
import_time_team() {
    print_status "Importing Time Team data to database..."
    docker compose --profile importer run --rm json-importer python json_importer.py --source time_team
    print_success "Time Team data imported successfully"
}

# Function to create database tables
create_tables() {
    print_status "Creating database tables..."
    docker compose --profile importer run --rm json-importer python json_importer.py --create-tables --source all
    print_success "Database tables created"
}

# Function to run migrations
migrate() {
    print_status "Running database migrations..."
    docker compose --profile importer run --rm json-importer alembic upgrade head
    print_success "Migrations completed"
}

# Function to show data status
show_status() {
    print_status "Checking data status..."
    
    echo ""
    echo "=== JSON Data Status ==="
    
    # Check KNRB data
    if [ -d "data/knrb_data" ]; then
        echo "KNRB Data:"
        find data/knrb_data -name "*.json" | wc -l | xargs echo "  Total JSON files:"
        echo "  Seasons: $(find data/knrb_data/seasons -name "*.json" 2>/dev/null | wc -l)"
        echo "  Tournaments: $(find data/knrb_data/tournaments -name "*.json" 2>/dev/null | wc -l)"
        echo "  Matches: $(find data/knrb_data/matches -name "*.json" 2>/dev/null | wc -l)"
        echo "  Races: $(find data/knrb_data/races -name "*.json" 2>/dev/null | wc -l)"
        echo "  Persons: $(find data/knrb_data/persons -name "*.json" 2>/dev/null | wc -l)"
    else
        echo "KNRB Data: Not found"
    fi
    
    echo ""
    # Check Time Team data
    if [ -d "data/time_team_data" ]; then
        echo "Time Team Data:"
        find data/time_team_data -name "*.json" | wc -l | xargs echo "  Total JSON files:"
        echo "  Regattas: $(find data/time_team_data/regattas -name "*.json" 2>/dev/null | wc -l)"
        echo "  Events: $(find data/time_team_data/events -name "*.json" 2>/dev/null | wc -l)"
        echo "  Races: $(find data/time_team_data/races -name "*.json" 2>/dev/null | wc -l)"
        echo "  Entries: $(find data/time_team_data/entries -name "*.json" 2>/dev/null | wc -l)"
        echo "  Clubs: $(find data/time_team_data/clubs -name "*.json" 2>/dev/null | wc -l)"
        echo "  Members: $(find data/time_team_data/members -name "*.json" 2>/dev/null | wc -l)"
    else
        echo "Time Team Data: Not found"
    fi
    
    echo ""
    echo "=== Database Status ==="
    docker compose --profile importer run --rm json-importer python -c "
from json_importer import JSONImporter
importer = JSONImporter()
summary = importer.get_import_summary()
for table, count in summary.items():
    print(f'  {table}: {count:,} records')
"
}

# Function to clean data directories
clean_data() {
    print_warning "This will remove all JSON data. Are you sure? (y/N)"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        print_status "Cleaning data directories..."
        rm -rf data/knrb_data/* data/time_team_data/*
        print_success "Data directories cleaned"
    else
        print_status "Operation cancelled"
    fi
}

# Main script logic
case "${1:-help}" in
    scrape-knrb)
        scrape_knrb "$2"
        ;;
    scrape-time-team)
        scrape_time_team "$2"
        ;;
    scrape-all)
        scrape_all "$2"
        ;;
    import-all)
        import_all
        ;;
    import-knrb)
        import_knrb
        ;;
    import-time-team)
        import_time_team
        ;;
    create-tables)
        create_tables
        ;;
    migrate)
        migrate
        ;;
    status)
        show_status
        ;;
    clean-data)
        clean_data
        ;;
    help|--help|-h)
        show_usage
        ;;
    *)
        print_error "Unknown command: $1"
        echo ""
        show_usage
        exit 1
        ;;
esac
