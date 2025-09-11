# KNRB Data Scraper

A comprehensive Python script for scraping KNRB (Koninklijke Nederlandse Roeibond) data from the Foys API. This unified script provides two main modes of operation:

1. **Full Scraping Mode**: Complete data scraping (seasons, tournaments, matches, races, persons, klassementen)
2. **Tournament Person Scraping Mode**: Fetch persons from specific tournaments only

## Features

### Core Functionality
- **Dual Mode Operation**: Full scraping or tournament-specific person fetching
- **Proxy Support**: Faster scraping without rate limiting when using proxy
- **Rate Limiting**: Optional 500ms interval when not using proxy
- **Multithreading**: Parallel processing for faster data collection
- **Database Connection Pooling**: Efficient database operations
- **Progress Tracking**: Comprehensive progress indicators with ETA
- **Error Handling**: Robust retry logic and error recovery
- **Resource Management**: Automatic cleanup of connections and sessions

### Data Processing
- **Smart Caching**: Skip already processed persons to avoid redundant API calls
- **Refetch Capability**: Option to refetch all persons from tournaments
- **Tournament Tracking**: Automatic marking of scanned tournaments
- **Data Validation**: JSON parsing with error handling
- **Immediate Persistence**: Data saved immediately to database

## Installation

### Prerequisites
- Python 3.8+
- PostgreSQL database
- Required Python packages (see requirements below)

### Setup
1. Clone or download the script
2. Install dependencies:
   ```bash
   pip install requests psycopg2-binary python-dotenv urllib3
   ```
3. Set up environment variables (create `.env` file):
   ```env
   DB_HOST=localhost
   DB_NAME=infomdss
   DB_USER=postgres
   DB_PASSWORD=your_password
   DB_PORT=5432
   PROXY_URL=http://your-proxy:port  # Optional, for faster scraping
   ```

## Usage

### Command Line Interface

The script supports two main modes:

#### Full Scraping Mode (Default)
Complete data scraping of all KNRB data:

```bash
# Basic full scraping
python knrb_scraper.py                           # Run complete scrape with proxy (fast)
python knrb_scraper.py --no-proxy                # Run without proxy (with rate limiting)
python knrb_scraper.py --workers 8               # Use 8 threads with proxy
python knrb_scraper.py --step seasons            # Run only seasons step
python knrb_scraper.py --step persons --workers 3 # Run persons with 3 threads
```

#### Tournament Person Scraping Mode
Fetch persons from specific tournaments only:

```bash
# Basic tournament person scraping
python knrb_scraper.py --tournament-mode --tournament-id "123e4567-e89b-12d3-a456-426614174000"
python knrb_scraper.py --tournament-mode --tournament-name "National Championships"

# Performance tuning for tournament mode
python knrb_scraper.py --tournament-mode --tournament-name "2024" --workers 8
python knrb_scraper.py --tournament-mode --tournament-name "2024" --workers 10 --pool-size 20

# Network configuration for tournament mode
python knrb_scraper.py --tournament-mode --tournament-name "Spring" --no-proxy

# Refetch all persons from tournament (even if already processed)
python knrb_scraper.py --tournament-mode --tournament-name "2024" --refetch-all
python knrb_scraper.py --tournament-mode --tournament-name "ARB Bosbaanwedstrijden 2024" --refetch-all --workers 5

# Combined options for maximum performance
python knrb_scraper.py --tournament-mode --tournament-name "2024" --refetch-all --workers 8 --pool-size 15 --no-proxy
```

### Command Line Arguments

#### Mode Selection
- `--tournament-mode`: Enable tournament person scraping mode (instead of full scraping)

#### Tournament Mode Specific
- `--tournament-id ID`: Process specific tournament by exact UUID
- `--tournament-name NAME`: Process tournament(s) by name with partial matching
- `--refetch-all`: Refetch all persons from tournament, even if already processed

#### Common Options
- `--workers N`: Number of concurrent threads (default: 5, recommended: 5-10)
- `--pool-size N`: Database connection pool size (default: 10)
- `--step STEP`: Run specific step only (seasons, tournaments, matches, persons, klassementen) - full mode only
- `--no-proxy`: Disable proxy usage and use rate limiting instead
- `--help`: Show detailed help message

## Full Scraping Mode

### Overview
The full scraping mode performs a complete data extraction from the KNRB API in 5 sequential steps:

1. **Seasons**: Fetch all available seasons
2. **Tournaments**: Fetch tournaments for each season
3. **Matches & Races**: Fetch matches and races for each tournament
4. **Persons**: Extract and fetch detailed person data from all races
5. **Klassementen**: Fetch ranking/classification data for all races

### Steps
Each step can be run individually using the `--step` argument:

```bash
python knrb_scraper.py --step seasons
python knrb_scraper.py --step tournaments
python knrb_scraper.py --step matches
python knrb_scraper.py --step persons
python knrb_scraper.py --step klassementen
```

### Progress Tracking
The full scraping mode provides detailed progress tracking:
- Real-time progress bars with percentages
- ETA calculations for remaining time
- Step-by-step completion times
- Final summary with data counts

## Tournament Person Scraping Mode

### Overview
The tournament person scraping mode allows you to fetch person data from specific tournaments without re-scraping the entire database. This is useful for:

- Adding new tournaments to your database
- Updating person data from specific events
- Refreshing data from tournaments that may have been updated

### Features
- **Tournament Selection**: Find tournaments by ID or name (partial matching)
- **Smart Processing**: Skip persons already in database
- **Refetch Option**: Option to refetch all persons even if already processed
- **Tournament Tracking**: Automatic marking of processed tournaments
- **Efficient Processing**: Only processes persons from selected tournaments

### Tournament Finding
Tournaments can be found by:
- **Exact ID**: `--tournament-id "123e4567-e89b-12d3-a456-426614174000"`
- **Name Pattern**: `--tournament-name "2024"` (finds all tournaments with "2024" in the name)

### Refetch Capability
The `--refetch-all` option allows you to:
- Refetch all persons from a tournament, even if already processed
- Update existing person data with fresh information
- Override the tournament's "scanned" status

## Database Schema

### Required Tables
The script expects the following PostgreSQL tables:

```sql
-- Seasons table
CREATE TABLE knrb_seasons (
    id UUID PRIMARY KEY,
    season_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tournaments table (with scanning flag)
CREATE TABLE knrb_tournaments (
    id UUID PRIMARY KEY,
    season_id UUID REFERENCES knrb_seasons(id),
    tournament_data JSONB,
    scanned_for_persons BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Matches table
CREATE TABLE knrb_matches (
    id UUID PRIMARY KEY,
    tournament_id UUID REFERENCES knrb_tournaments(id),
    match_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Races table
CREATE TABLE knrb_races (
    id UUID PRIMARY KEY,
    match_id UUID REFERENCES knrb_matches(id),
    race_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Persons table
CREATE TABLE knrb_persons (
    id UUID PRIMARY KEY,
    person_data JSONB,
    race_overview_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Klassementen table
CREATE TABLE knrb_klassementen (
    id UUID PRIMARY KEY,
    race_id UUID REFERENCES knrb_races(id),
    klassement_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Klassement details table
CREATE TABLE knrb_klassement_details (
    id UUID PRIMARY KEY,
    klassement_id UUID REFERENCES knrb_klassementen(id),
    klassement_detail_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for tournament scanning
CREATE INDEX idx_knrb_tournaments_scanned_for_persons ON knrb_tournaments (scanned_for_persons);
```

### Tournament Scanning Flag
The `scanned_for_persons` boolean flag in the `knrb_tournaments` table tracks which tournaments have been processed for person data. This allows the script to:
- Skip tournaments that have already been processed
- Identify new tournaments that need person data
- Support incremental updates

## Configuration

### Environment Variables
Create a `.env` file in the script directory:

```env
# Database configuration
DB_HOST=localhost
DB_NAME=infomdss
DB_USER=postgres
DB_PASSWORD=your_password
DB_PORT=5432

# Proxy configuration (optional)
PROXY_URL=http://your-proxy:port
```

### Proxy Configuration
The script supports HTTP/HTTPS proxies for faster scraping:
- **With Proxy**: No rate limiting, faster processing
- **Without Proxy**: 500ms rate limiting between requests

### Performance Tuning
- **Workers**: Increase `--workers` for more parallel processing (recommended: 5-10)
- **Pool Size**: Increase `--pool-size` for more database connections (default: 10)
- **Proxy**: Use proxy for faster API requests without rate limiting

## Logging

### Log Files
- **Console Output**: Real-time progress and status updates
- **Log File**: Detailed logs written to `knrb_scraper.log`

### Log Levels
- **INFO**: General progress and status information
- **DEBUG**: Detailed debugging information
- **WARNING**: Non-critical issues
- **ERROR**: Critical errors that may cause failures

## Error Handling

### Retry Logic
- **Network Errors**: Automatic retry with exponential backoff
- **Proxy Issues**: Detection and retry for proxy-related 404 errors
- **JSON Parsing**: Graceful handling of invalid JSON responses
- **Database Errors**: Connection pool management and error recovery

### Common Issues
1. **Database Connection**: Ensure PostgreSQL is running and credentials are correct
2. **Proxy Issues**: Check proxy URL and connectivity
3. **Rate Limiting**: Use proxy or reduce worker count if hitting rate limits
4. **Memory Usage**: Large datasets may require more memory

## Examples

### Complete Data Scraping
```bash
# Full scrape with proxy (recommended)
python knrb_scraper.py --workers 8

# Full scrape without proxy (slower but more reliable)
python knrb_scraper.py --no-proxy --workers 3
```

### Tournament-Specific Person Fetching
```bash
# Fetch persons from all 2024 tournaments
python knrb_scraper.py --tournament-mode --tournament-name "2024" --workers 5

# Refetch all persons from a specific tournament
python knrb_scraper.py --tournament-mode --tournament-name "ARB Bosbaanwedstrijden 2024" --refetch-all

# Fetch persons from tournament by exact ID
python knrb_scraper.py --tournament-mode --tournament-id "00000000-0000-0000-0000-000000000c00"
```

### Step-by-Step Processing
```bash
# Run only specific steps
python knrb_scraper.py --step seasons
python knrb_scraper.py --step tournaments
python knrb_scraper.py --step matches
python knrb_scraper.py --step persons --workers 8
python knrb_scraper.py --step klassementen
```

## Performance Tips

### Full Scraping Mode
- Use proxy for faster API requests
- Increase workers (5-10) for parallel processing
- Monitor memory usage for large datasets
- Run during off-peak hours to avoid rate limits

### Tournament Person Scraping Mode
- Use `--refetch-all` sparingly (only when needed)
- Process tournaments in batches for better performance
- Use proxy for faster person data fetching
- Monitor database connection pool usage

## Troubleshooting

### Common Problems

1. **"Database connection failed"**
   - Check PostgreSQL is running
   - Verify database credentials in `.env` file
   - Ensure database exists

2. **"No tournaments found"**
   - Run full scraping mode first to populate tournaments
   - Check tournament name spelling
   - Verify tournament ID format (UUID)

3. **"Proxy 404 errors"**
   - Check proxy URL configuration
   - Verify proxy server is accessible
   - Try without proxy using `--no-proxy`

4. **"Rate limit exceeded"**
   - Use proxy for faster scraping
   - Reduce number of workers
   - Add delays between requests

### Getting Help
- Use `--help` for detailed command line options
- Check log files for detailed error information
- Verify environment variables are set correctly
- Ensure all required dependencies are installed

## License

This script is provided as-is for educational and research purposes. Please respect the KNRB API terms of service and implement appropriate rate limiting when using without a proxy.
