#!/usr/bin/env python3
"""
KNRB Data Scraper Script

A comprehensive script for scraping KNRB (Koninklijke Nederlandse Roeibond) data
from the Foys API with two main modes:

1. Full Scraping Mode: Complete data scraping (seasons, tournaments, matches, races, persons)
2. Tournament Mode: Run full scrape but only for unscanned tournaments

Features:
- Proxy support for faster scraping without rate limiting
- Optional rate limiting (500ms interval) when not using proxy
- Multithreading for parallel processing
- Comprehensive progress indicators with ETA
- Database connection pooling
- Error handling and retry logic
- Resource cleanup
- Tournament scanning status tracking
- Refetch all persons from unscanned tournaments

Usage:
    # Full scraping mode
    python knrb_scraper.py [--workers N] [--pool-size N] [--step STEP] [--no-proxy]
    
    # Tournament mode (unscanned tournaments only)
    python knrb_scraper.py --tournament-mode [--workers N] [--pool-size N] [--no-proxy]
    
Options:
    --tournament-mode        Enable tournament mode: run full scrape for unscanned tournaments only
    --workers N             Number of concurrent threads (default: 5)
    --pool-size N           Database connection pool size (default: 10)
    --step STEP             Run specific step only (seasons, tournaments, matches, persons)
    --no-proxy              Disable proxy and use rate limiting instead
    --help                  Show this help message

Examples:
    # Full scraping
    python knrb_scraper.py                           # Run complete scrape
    python knrb_scraper.py --workers 8               # Use 8 threads
    python knrb_scraper.py --step seasons            # Run only seasons step
    python knrb_scraper.py --step persons --workers 3 # Run persons with 3 threads
    
    # Tournament mode (unscanned tournaments only)
    python knrb_scraper.py --tournament-mode         # Run full scrape for unscanned tournaments
    python knrb_scraper.py --tournament-mode --workers 8  # Use 8 threads for tournament mode
    python knrb_scraper.py --tournament-mode --no-proxy   # Tournament mode without proxy
"""

import os
import sys
import argparse
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
import uuid
import time
import gc
import json
import requests
from typing import List, Dict, Set, Optional
from threading import Lock
import psycopg2
from psycopg2 import pool
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv
from contextlib import contextmanager

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('knrb_scraper.log')
    ]
)
logger = logging.getLogger(__name__)

# turn off logging
logging.disable(logging.INFO)

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'infomdss'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'password'),
    'port': os.getenv('DB_PORT', '5432')
}

def get_connection():
    """Create database connection"""
    return psycopg2.connect(**DB_CONFIG)

class KNRBDataScraper:
    """KNRB Data Scraper with progress tracking and optimized performance"""
    
    def __init__(self, max_workers: int = 5, connection_pool_size: int = 10, use_proxy: bool = True):
        self.base_url = "https://api.foys.io/tournament/public/api/v1"
        self.federation_id = "348625af-0eff-47b7-80d6-dfa6b5a8ad19"
        self.max_workers = max_workers
        self.connection_pool_size = connection_pool_size
        self.use_proxy = use_proxy
        
        # Thread-safe person cache to avoid duplicate processing
        self.processed_persons: Set[str] = set()
        self.person_cache_lock = Lock()
        
        # Connection pool for database operations
        self.connection_pool = None
        self._init_connection_pool()
        
        # Rate limiting - disabled when using proxy
        self.use_rate_limiting = not use_proxy  # Disabled with proxy
        self.request_lock = Lock()
        self.last_request_time = 0
        self.min_request_interval = 0.5  # 500ms between requests (not used with proxy)
        
        # Initialize session with retry strategy
        self.session = self._create_session_with_retries()
        
        proxy_status = "with proxy (no rate limiting)" if use_proxy else "without proxy (with rate limiting)"
        logger.info(f"KNRB Data Scraper initialized with {max_workers} workers, {connection_pool_size} connections, {proxy_status}")
    
    # ---------------------------------------------------------------------
    # Shared helpers
    # ---------------------------------------------------------------------
    @staticmethod
    def _to_uuid(value: Optional[object]) -> Optional[uuid.UUID]:
        """Convert various inputs (str/uuid/int) into uuid.UUID where possible."""
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        if isinstance(value, int):
            # Deterministic conversion, preserves previous behavior
            return uuid.UUID(int=value)
        if isinstance(value, str):
            try:
                return uuid.UUID(value)
            except Exception:
                # As a fallback, try to treat numeric-like strings as ints
                try:
                    return uuid.UUID(int=int(value))
                except Exception:
                    raise
        raise TypeError(f"Unsupported UUID value type: {type(value)}")

    @contextmanager
    def _db_cursor(self):
        """Context manager that yields (conn, cursor) and commits on successful exit."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                yield conn, cursor
            conn.commit()
        finally:
            self._return_connection(conn)

    def _fetch_json(self, url: str, params: Optional[Dict] = None, allow_404: bool = True) -> Optional[object]:
        """Wrapper around HTTP GET that returns parsed JSON or None on 404 when allowed."""
        response = self._make_request_with_retry(url, params=params)
        if allow_404 and response.status_code == 404:
            return None
        if not response.text.strip():
            return None
        try:
            return response.json()
        except json.JSONDecodeError:
            logger.debug(f"Invalid JSON at {url}")
            return None

    def _insert_or_update(self, cursor, table: str, data: Dict[str, object], conflict_columns: List[str] = ["id"], do_update: bool = True):
        """
        Generic UPSERT helper.
        - If do_update is False, uses DO NOTHING on conflict.
        - Otherwise, updates all non-conflict columns via EXCLUDED and bumps updated_at when present.
        """
        columns = list(data.keys())
        placeholders = ", ".join(["%s"] * len(columns))
        def _as_sql_value(v):
            return str(v) if isinstance(v, uuid.UUID) else v
        values = [_as_sql_value(data[c]) for c in columns]

        if do_update:
            updatable = [c for c in columns if c not in conflict_columns]
            set_parts = [f"{c} = EXCLUDED.{c}" for c in updatable]
            # Attempt to maintain updated_at behavior when table has such a column
            set_parts.append("updated_at = CURRENT_TIMESTAMP")
            set_clause = ", ".join(set_parts)
            sql = (
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
                f"ON CONFLICT ({', '.join(conflict_columns)}) DO UPDATE SET {set_clause}"
            )
        else:
            sql = (
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
                f"ON CONFLICT ({', '.join(conflict_columns)}) DO NOTHING"
            )

        cursor.execute(sql, values)

    def _process_person(self, cursor, conn, person_data: Dict, refetch_all: bool = False) -> bool:
        """Process a single person: insert basic, update detailed, update race overview."""
        person_id = person_data.get('personId')
        if not person_id:
            return False

        db_person_id = self._to_uuid(person_id)

        # Skip if already processed
        if not refetch_all and self._is_person_processed(str(db_person_id)):
            return False

        cursor.execute(
            """
            SELECT person_data, race_overview_data 
            FROM knrb_persons 
            WHERE id = %s
            """,
            (str(db_person_id),)
        )
        existing_data = cursor.fetchone()

        # Store/refresh basic person data when missing or refetching all
        if not existing_data or not existing_data[0] or refetch_all:
            self._insert_or_update(
                cursor,
                table="knrb_persons",
                data={
                    "id": db_person_id,
                    "person_data": json.dumps(person_data),
                },
                conflict_columns=["id"],
                do_update=True,
            )
            # Commit basic data immediately to ensure intermediate save
            conn.commit()

        # Fetch detailed person data if needed
        if not existing_data or not existing_data[0] or refetch_all:
            try:
                detailed_person_data = self._fetch_json(f"{self.base_url}/persons/{person_id}")
                if detailed_person_data is not None:
                    cursor.execute(
                        """
                        UPDATE knrb_persons 
                        SET person_data = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        """,
                        (json.dumps(detailed_person_data), str(db_person_id))
                    )
                    # Commit detailed data update
                    conn.commit()
            except Exception as e:
                logger.warning(f"Failed to fetch/update detailed person {person_id}: {e}")

        # Fetch race overview if needed
        if not existing_data or not existing_data[1] or refetch_all:
            try:
                race_overview_data = self._fetch_json(f"{self.base_url}/races/person-overview-results/{person_id}")
                if race_overview_data is not None:
                    cursor.execute(
                        """
                        UPDATE knrb_persons 
                        SET race_overview_data = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        """,
                        (json.dumps(race_overview_data), str(db_person_id))
                    )
                    # Commit race overview update
                    conn.commit()
            except Exception as e:
                logger.warning(f"Failed to fetch/update race overview for person {person_id}: {e}")

        self._mark_person_processed(str(db_person_id))
        return True
    
    def _create_session_with_retries(self):
        """Create a requests session with optional proxy configuration"""
        session = requests.Session()
        
        if self.use_proxy:
            # Configure proxy for faster scraping without rate limiting
            proxy_url = os.getenv('PROXY_URL')
            if proxy_url:
                proxy_config = {
                    'http': proxy_url,
                    'https': proxy_url
                }
                session.proxies.update(proxy_config)
                logger.info(f"Proxy configured: {proxy_url}")
            else:
                logger.warning("Proxy enabled but PROXY_URL not found in environment variables")
            
            # Disable SSL verification for proxy compatibility
            session.verify = False
            
            # Suppress SSL warnings
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            logger.info("Using proxy for faster scraping without rate limiting")
        else:
            # Use standard session with retry strategy
            retry_strategy = Retry(
                total=5,
                status_forcelist=[429, 500, 502, 503, 504],
                backoff_factor=2,
                raise_on_status=False
            )
            
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            
            logger.info("Using standard session with rate limiting")
        
        # Set timeout
        session.timeout = 30
        
        # Add headers that might help with proxy compatibility
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
        return session
    
    def _make_request_with_retry(self, url, params=None, max_retries=3, backoff_factor=1):
        """Make HTTP request with optional rate limiting"""
        for attempt in range(max_retries + 1):
            try:
                # Apply rate limiting only when enabled (disabled with proxy)
                if self.use_rate_limiting:
                    self._rate_limit()
                
                response = self.session.get(url, params=params, timeout=30)
                
                # Check if we got an HTML response instead of JSON (proxy issue)
                content_type = response.headers.get('content-type', '').lower()
                if 'text/html' in content_type and 'application/json' not in content_type:
                    # If it's a 404 with HTML from proxy, retry since proxy switches servers
                    if response.status_code == 404:
                        logger.info(f"404 HTML response from proxy for {url} - retrying (proxy may switch servers)")
                        raise requests.exceptions.RequestException(f"Proxy 404 HTML response - retrying")
                    else:
                        logger.warning(f"Received HTML response instead of JSON from {url} - possible proxy issue")
                        logger.debug(f"Response content: {response.text[:200]}...")
                        response.raise_for_status()  # Raise for non-404 HTML responses
                else:
                    # Only raise for status for non-404 responses
                    if response.status_code != 404:
                        response.raise_for_status()
                
                # Log successful requests
                logger.info(f"✅ Successfully fetched {url} - Status: {response.status_code}")
                return response
            except (requests.exceptions.ConnectionError, 
                    requests.exceptions.Timeout,
                    requests.exceptions.RequestException) as e:
                if attempt == max_retries:
                    logger.warning(f"Failed to fetch {url} after {max_retries + 1} attempts: {e}")
                    raise
                else:
                    wait_time = backoff_factor ** attempt
                    logger.info(f"Request failed (attempt {attempt + 1}/{max_retries + 1}), retrying in {wait_time}s: {e}")
                    # time.sleep(wait_time)
    
    def _init_connection_pool(self):
        """Initialize database connection pool"""
        try:
            self.connection_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=self.connection_pool_size,
                **DB_CONFIG
            )
            logger.info(f"Connection pool initialized with {self.connection_pool_size} connections")
        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            raise
    
    def _get_connection(self):
        """Get connection from pool"""
        if self.connection_pool:
            return self.connection_pool.getconn()
        else:
            return get_connection()
    
    def _return_connection(self, conn):
        """Return connection to pool"""
        if self.connection_pool:
            self.connection_pool.putconn(conn)
        else:
            conn.close()
    
    def _rate_limit(self):
        """Thread-safe rate limiting - disabled with proxy"""
        if not self.use_rate_limiting:
            return  # No rate limiting when using proxy
        
        with self.request_lock:
            current_time = time.time()
            time_since_last = current_time - self.last_request_time
            if time_since_last < self.min_request_interval:
                time.sleep(self.min_request_interval - time_since_last)
            self.last_request_time = time.time()
    
    def _print_progress(self, current: int, total: int, operation: str, start_time: datetime = None):
        """Print progress indicator with percentage and ETA"""
        if total == 0:
            return
        
        percentage = (current / total) * 100
        bar_length = 30
        filled_length = int(bar_length * current // total)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        
        # Calculate ETA if start_time is provided
        eta_str = ""
        if start_time and current > 0:
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = current / elapsed
            if rate > 0:
                remaining = (total - current) / rate
                eta_str = f" | ETA: {remaining:.0f}s"
        
        print(f"\r{operation}: |{bar}| {current}/{total} ({percentage:.1f}%){eta_str}", end='', flush=True)
        
        if current == total:
            print()  # New line when complete
    
    def _load_processed_persons(self):
        """Load already processed person IDs from database"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM knrb_persons")
                with self.person_cache_lock:
                    self.processed_persons = {str(row[0]) for row in cursor.fetchall()}
                logger.info(f"Loaded {len(self.processed_persons)} already processed persons")
        finally:
            self._return_connection(conn)
    
    def _is_person_processed(self, person_id: str) -> bool:
        """Check if person is already processed (thread-safe)"""
        with self.person_cache_lock:
            return person_id in self.processed_persons
    
    def _mark_person_processed(self, person_id: str):
        """Mark person as processed (thread-safe)"""
        with self.person_cache_lock:
            self.processed_persons.add(person_id)
    
    # ============================================================================
    # FULL SCRAPING MODE METHODS
    # ============================================================================
    
    def fetch_and_store_seasons(self):
        """Fetch and store all seasons data"""
        logger.info("Fetching seasons data...")
        print("📅 Fetching seasons...")
        
        try:
            seasons_data = self._fetch_json(f"{self.base_url}/seasons", params={"federationId": self.federation_id}) or {}
            items = seasons_data.get('items', [])

            with self._db_cursor() as (conn, cursor):
                for season in items:
                    raw_id = season.get('id')
                    db_season_id = self._to_uuid(raw_id)
                    self._insert_or_update(
                        cursor,
                        table="knrb_seasons",
                        data={
                            "id": db_season_id,
                            "season_data": json.dumps(season),
                        },
                        conflict_columns=["id"],
                        do_update=True,
                    )

            logger.info(f"Stored {len(items)} seasons")
            print(f"✅ Stored {len(items)} seasons")

            essential_seasons = [{'id': s['id'], 'name': s.get('name', 'Unknown')} for s in items]
            del seasons_data
            gc.collect()
            
            return essential_seasons
        except Exception as e:
            logger.error(f"Error fetching seasons: {e}")
            print(f"❌ Error fetching seasons: {e}")
            raise
    
    def fetch_and_store_tournaments(self, seasons: List[Dict], tournament_mode: bool = False):
        """Fetch and store tournaments for all seasons using multithreading"""
        logger.info("Fetching tournaments data with multithreading...")
        print("🏆 Fetching tournaments...")
        start_time = datetime.now()
        
        def process_season(season):
            """Process a single season"""
            try:
                params = {
                    'federationId': self.federation_id,
                    'seasonId': season['id'],
                    'pageSize': 1000,
                    'registrationsFilter': False,
                    'resultsFilter': True
                }
                tournaments_data = self._fetch_json(f"{self.base_url}/tournaments", params=params) or {}
                items = tournaments_data.get('items', [])

                with self._db_cursor() as (conn, cursor):
                    db_season_id = self._to_uuid(season['id'])
                    for tournament in items:
                        db_tournament_id = self._to_uuid(tournament.get('id'))
                        self._insert_or_update(
                            cursor,
                            table="knrb_tournaments",
                            data={
                                "id": db_tournament_id,
                                "season_id": db_season_id,
                                "tournament_data": json.dumps(tournament),
                                "scanned_for_persons": False,  # Always mark as unscanned initially
                            },
                            conflict_columns=["id"],
                            do_update=True,
                        )

                logger.info(f"Stored {len(items)} tournaments for season {season.get('name')}")
                return len(items), season.get('name')
            except Exception as e:
                logger.error(f"Error processing season {season.get('name')}: {e}")
                return 0, season.get('name')
        
        # Process seasons in parallel with progress tracking
        total_tournaments = 0
        completed_seasons = 0
        total_seasons = len(seasons)
        
        print(f"🏆 Processing {total_seasons} seasons...")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_season = {executor.submit(process_season, season): season for season in seasons}
            
            for future in as_completed(future_to_season):
                tournament_count, season_name = future.result()
                total_tournaments += tournament_count
                completed_seasons += 1
                
                self._print_progress(completed_seasons, total_seasons, "Seasons", start_time)
                print(f"  - Season {season_name}: {tournament_count} tournaments")
        
        print(f"✅ Total tournaments stored: {total_tournaments}")
    
    def fetch_and_store_matches_and_races(self, tournament_mode: bool = False):
        """Fetch and store matches and races using multithreading"""
        logger.info("Fetching matches and races data with multithreading...")
        print("🏁 Fetching matches and races...")
        start_time = datetime.now()
        
        def process_tournament_batch(tournament_batch):
            """Process a batch of tournaments"""
            total_matches = 0
            total_races = 0
            
            with self._db_cursor() as (conn, cursor):
                for tournament_id, original_tournament_id, tournament_name in tournament_batch:
                    try:
                        params = {
                            'tournamentId': original_tournament_id,
                            'raceResults': True,
                            'orderByMatchBoatCategoryCodes': True
                        }
                        matches_data = self._fetch_json(f"{self.base_url}/matches", params=params) or []

                        match_count = 0
                        race_count = 0

                        for match in matches_data:
                            db_match_id = self._to_uuid(match.get('id'))
                            self._insert_or_update(
                                cursor,
                                table="knrb_matches",
                                data={
                                    "id": db_match_id,
                                    "tournament_id": tournament_id,
                                    "match_data": json.dumps(match),
                                },
                                conflict_columns=["id"],
                                do_update=True,
                            )
                            match_count += 1

                            for race in match.get('races', []):
                                db_race_id = self._to_uuid(race.get('id'))
                                self._insert_or_update(
                                    cursor,
                                    table="knrb_races",
                                    data={
                                        "id": db_race_id,
                                        "match_id": db_match_id,
                                        "race_data": json.dumps(race),
                                    },
                                    conflict_columns=["id"],
                                    do_update=True,
                                )
                                race_count += 1

                        total_matches += match_count
                        total_races += race_count

                        # free memory
                        del matches_data

                    except Exception as e:
                        logger.warning(f"Failed to fetch matches for tournament {original_tournament_id}: {e}")
                        continue
                
                return total_matches, total_races
        
        # Get tournaments based on mode
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                if tournament_mode:
                    # Only get unscanned tournaments in tournament mode
                    cursor.execute("""
                        SELECT id, tournament_data->>'id' as original_id, tournament_data->>'name' as name 
                        FROM knrb_tournaments 
                        WHERE scanned_for_persons = FALSE
                        ORDER BY id
                    """)
                    all_tournaments = cursor.fetchall()
                    print(f"🏁 Processing {len(all_tournaments)} unscanned tournaments for matches and races...")
                else:
                    # Get all tournaments in normal mode
                    cursor.execute("SELECT COUNT(*) FROM knrb_tournaments")
                    total_tournament_count = cursor.fetchone()[0]
                    print(f"🏁 Processing {total_tournament_count} tournaments for matches and races...")
                    
                    cursor.execute("""
                        SELECT id, tournament_data->>'id' as original_id, tournament_data->>'name' as name 
                        FROM knrb_tournaments 
                        ORDER BY id
                    """)
                    all_tournaments = cursor.fetchall()
        finally:
            self._return_connection(conn)
        
        if not all_tournaments:
            print("✅ No tournaments to process for matches and races")
            return
        
        # Process tournaments in parallel batches with progress tracking
        batch_size = max(1, len(all_tournaments) // (self.max_workers * 2))
        tournament_batches = [all_tournaments[i:i + batch_size] for i in range(0, len(all_tournaments), batch_size)]
        
        total_matches = 0
        total_races = 0
        completed_batches = 0
        total_batches = len(tournament_batches)
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_batch = {executor.submit(process_tournament_batch, batch): batch for batch in tournament_batches}
            
            for future in as_completed(future_to_batch):
                matches, races = future.result()
                total_matches += matches
                total_races += races
                completed_batches += 1
                
                self._print_progress(completed_batches, total_batches, "Tournament Batches", start_time)
        
        print(f"✅ Total stored - Matches: {total_matches}, Races: {total_races}")
    
    def fetch_and_store_persons(self, tournament_mode: bool = False):
        """Extract and store person data using multithreading with caching"""
        logger.info("Extracting and storing person data with multithreading...")
        print("👥 Processing persons...")
        start_time = datetime.now()
        
        # Load already processed persons (only in normal mode)
        if not tournament_mode:
            self._load_processed_persons()
        
        def process_person_batch(person_batch):
            """Process a batch of persons"""
            processed_count = 0
            logger.info(f"🔄 Processing batch of {len(person_batch)} persons")
            with self._db_cursor() as (conn, cursor):
                for person_data in person_batch:
                    try:
                        # In tournament mode, always refetch all persons
                        processed = self._process_person(cursor, conn, person_data, refetch_all=tournament_mode)
                        if processed:
                            processed_count += 1
                    except Exception as e:
                        logger.warning(f"Failed processing person in batch: {e}")
                        continue
            return processed_count
        
        # Get unique person data based on mode
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                if tournament_mode:
                    # In tournament mode, get persons from unscanned tournaments only
                    cursor.execute("""
                        SELECT DISTINCT jsonb_array_elements(
                            jsonb_path_query_array(
                                r.race_data, 
                                '$.raceTeams[*].teamVersion.teamMembers[*].person'
                            )
                        ) as person_data
                        FROM knrb_races r
                        JOIN knrb_matches m ON m.id = r.match_id
                        JOIN knrb_tournaments t ON t.id = m.tournament_id
                        WHERE t.scanned_for_persons = FALSE
                    """)
                else:
                    # In normal mode, get all persons
                    cursor.execute("""
                        SELECT DISTINCT jsonb_array_elements(
                            jsonb_path_query_array(
                                race_data, 
                                '$.raceTeams[*].teamVersion.teamMembers[*].person'
                            )
                        ) as person_data
                        FROM knrb_races
                    """)
                
                all_persons = []
                for row in cursor:
                    person_data = row[0]
                    person_id = person_data.get('personId')
                    if not person_id:
                        continue
                    
                    # Convert to consistent format for caching
                    if isinstance(person_id, int):
                        db_person_id = str(uuid.UUID(int=person_id))
                    else:
                        db_person_id = person_id
                    
                    # Skip if already processed (only in normal mode)
                    if not tournament_mode and self._is_person_processed(db_person_id):
                        continue
                    
                    all_persons.append(person_data)
        finally:
            self._return_connection(conn)
        
        if tournament_mode:
            print(f"👥 Found {len(all_persons)} persons to refetch from unscanned tournaments")
        else:
            print(f"👥 Found {len(all_persons)} new persons to process")
        
        if not all_persons:
            print("✅ No persons to process")
            return
        
        # Process persons in parallel batches with progress tracking
        batch_size = max(10, len(all_persons) // (self.max_workers * 4))
        person_batches = [all_persons[i:i + batch_size] for i in range(0, len(all_persons), batch_size)]
        
        total_processed = 0
        completed_batches = 0
        total_batches = len(person_batches)
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_batch = {executor.submit(process_person_batch, batch): batch for batch in person_batches}
            
            for future in as_completed(future_to_batch):
                processed_count = future.result()
                total_processed += processed_count
                completed_batches += 1
                
                self._print_progress(completed_batches, total_batches, "Person Batches", start_time)
        
        if tournament_mode:
            print(f"✅ Refetched {total_processed} persons from unscanned tournaments")
        else:
            print(f"✅ Processed {total_processed} new persons successfully")
        
        # Mark tournaments as scanned for persons
        if tournament_mode:
            self._mark_unscanned_tournaments_scanned()
        else:
            self._mark_all_tournaments_scanned()
    
    def _mark_all_tournaments_scanned(self):
        """Mark all tournaments as scanned for persons"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE knrb_tournaments 
                    SET scanned_for_persons = TRUE, updated_at = CURRENT_TIMESTAMP
                    WHERE scanned_for_persons = FALSE
                """)
                updated_count = cursor.rowcount
                conn.commit()
                logger.info(f"✅ Marked {updated_count} tournaments as scanned for persons")
                print(f"✅ Marked {updated_count} tournaments as scanned for persons")
        finally:
            self._return_connection(conn)
    
    def _mark_unscanned_tournaments_scanned(self):
        """Mark unscanned tournaments as scanned for persons"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE knrb_tournaments 
                    SET scanned_for_persons = TRUE, updated_at = CURRENT_TIMESTAMP
                    WHERE scanned_for_persons = FALSE
                """)
                updated_count = cursor.rowcount
                conn.commit()
                logger.info(f"✅ Marked {updated_count} unscanned tournaments as scanned for persons")
                print(f"✅ Marked {updated_count} unscanned tournaments as scanned for persons")
        finally:
            self._return_connection(conn)
    
    def run_full_scrape_with_progress(self, tournament_mode: bool = False):
        """Run the complete data scraping process with comprehensive progress tracking"""
        mode_text = "tournament mode (unscanned tournaments only)" if tournament_mode else "full scrape"
        print(f"🚀 Starting KNRB data scrape in {mode_text}...")
        overall_start_time = datetime.now()
        
        try:
            # Step 1: Fetch and store seasons
            print("\n" + "="*60)
            print("📅 STEP 1: Fetching seasons...")
            print("="*60)
            step_start = datetime.now()
            seasons = self.fetch_and_store_seasons()
            step_duration = datetime.now() - step_start
            print(f"✅ Step 1 completed in {step_duration.total_seconds():.1f}s")
            
            # Step 2: Fetch and store tournaments
            print("\n" + "="*60)
            print("🏆 STEP 2: Fetching tournaments...")
            print("="*60)
            step_start = datetime.now()
            self.fetch_and_store_tournaments(seasons, tournament_mode)
            step_duration = datetime.now() - step_start
            print(f"✅ Step 2 completed in {step_duration.total_seconds():.1f}s")
            
            # Step 3: Fetch and store matches and races
            print("\n" + "="*60)
            print("🏁 STEP 3: Fetching matches and races...")
            print("="*60)
            step_start = datetime.now()
            self.fetch_and_store_matches_and_races(tournament_mode)
            step_duration = datetime.now() - step_start
            print(f"✅ Step 3 completed in {step_duration.total_seconds():.1f}s")
            
            # Step 4: Fetch and store persons
            print("\n" + "="*60)
            print("👥 STEP 4: Processing persons...")
            print("="*60)
            step_start = datetime.now()
            self.fetch_and_store_persons(tournament_mode)
            step_duration = datetime.now() - step_start
            print(f"✅ Step 4 completed in {step_duration.total_seconds():.1f}s")
            
            # Final summary
            overall_duration = datetime.now() - overall_start_time
            print("\n" + "="*60)
            if tournament_mode:
                print("🎉 TOURNAMENT MODE SCRAPE COMPLETED SUCCESSFULLY!")
            else:
                print("🎉 FULL SCRAPE COMPLETED SUCCESSFULLY!")
            print("="*60)
            print(f"⏱️ Total duration: {overall_duration}")
            print(f"📊 Average time per step: {overall_duration.total_seconds() / 4:.1f}s")
            
            # Show summary statistics
            print("\n📊 Data Summary:")
            conn = self._get_connection()
            try:
                with conn.cursor() as cursor:
                    tables = ['knrb_seasons', 'knrb_tournaments', 'knrb_matches', 'knrb_races', 'knrb_persons']
                    for table in tables:
                        cursor.execute(f"SELECT COUNT(*) FROM {table}")
                        count = cursor.fetchone()[0]
                        print(f"  - {table}: {count:,} records")
            finally:
                self._return_connection(conn)
                
        except Exception as e:
            print(f"❌ Error during scrape: {e}")
            logger.error(f"Error during scrape: {e}")
            raise
    
    
    def close(self):
        """Close connection pool and session"""
        if self.connection_pool:
            self.connection_pool.closeall()
            logger.info("Connection pool closed")
        if hasattr(self, 'session'):
            self.session.close()
            logger.info("HTTP session closed")

def main():
    """Main function to run the KNRB scraper"""
    parser = argparse.ArgumentParser(
        description="KNRB Data Scraper - Comprehensive data scraping with tournament mode for unscanned tournaments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
FEATURES:
  • Full data scraping: seasons, tournaments, matches, races, persons
  • Tournament mode: run full scrape but only for unscanned tournaments
  • Skip already processed persons to avoid redundant API calls (normal mode)
  • Refetch all persons from unscanned tournaments (tournament mode)
  • Proxy support with automatic retry for failed requests
  • Multithreaded processing for faster data collection
  • Database connection pooling for efficient database operations
  • Comprehensive logging with detailed progress tracking
  • Automatic tournament scanning status tracking

EXAMPLES:
  # Normal full scraping (all tournaments)
  python knrb_scraper.py                           # Run complete scrape with proxy (fast)
  python knrb_scraper.py --no-proxy                # Run without proxy (with rate limiting)
  python knrb_scraper.py --workers 8               # Use 8 threads with proxy
  python knrb_scraper.py --step seasons            # Run only seasons step
  python knrb_scraper.py --step persons --workers 3 # Run persons with 3 threads

  # Tournament mode (unscanned tournaments only)
  python knrb_scraper.py --tournament-mode         # Run full scrape for unscanned tournaments only
  python knrb_scraper.py --tournament-mode --workers 8  # Use 8 threads for tournament mode
  python knrb_scraper.py --tournament-mode --no-proxy   # Tournament mode without proxy

DATABASE SCHEMA:
  The script uses a 'scanned_for_persons' boolean flag in the knrb_tournaments table
  to track which tournaments have been processed for person data.

LOGGING:
  Detailed logs are written to 'knrb_scraper.log' with progress
  information, API request status, and database operations.
        """
    )
    
    # Mode selection
    parser.add_argument(
        '--tournament-mode', 
        action='store_true',
        help='Enable tournament mode: run full scrape but only for unscanned tournaments'
    )
    
    # Common arguments
    parser.add_argument(
        '--workers', 
        type=int, 
        default=5, 
        help='Number of concurrent threads for parallel processing (default: 5, recommended: 5-10)'
    )
    
    parser.add_argument(
        '--pool-size', 
        type=int, 
        default=10, 
        help='Database connection pool size for concurrent database operations (default: 10)'
    )
    
    parser.add_argument(
        '--step', 
        choices=['seasons', 'tournaments', 'matches', 'persons'],
        help='Run specific step only (not available in tournament mode)'
    )
    
    parser.add_argument(
        '--no-proxy', 
        action='store_true',
        help='Disable proxy usage and use rate limiting instead (useful for direct API access)'
    )
    
    args = parser.parse_args()
    
    # Validate arguments based on mode
    if args.tournament_mode and args.step:
        parser.error("--step is not available in tournament mode")
    
    # Validate database connection
    try:
        conn = get_connection()
        conn.close()
        logger.info("Database connection validated")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        print(f"❌ Database connection failed: {e}")
        print("💡 Make sure your database is running and environment variables are set correctly")
        sys.exit(1)
    
    # Initialize scraper
    use_proxy = not args.no_proxy  # Use proxy by default, disable with --no-proxy flag
    scraper = KNRBDataScraper(max_workers=args.workers, connection_pool_size=args.pool_size, use_proxy=use_proxy)
    
    try:
        if args.tournament_mode:
            # Tournament mode: run full scrape for unscanned tournaments only
            print("🎯 Starting tournament mode: full scrape for unscanned tournaments only...")
            scraper.run_full_scrape_with_progress(tournament_mode=True)
        else:
            # Normal full scraping mode
            if args.step:
                # Run specific step
                print(f"🔧 Running step: {args.step}")
                
                if args.step == 'seasons':
                    scraper.fetch_and_store_seasons()
                elif args.step == 'tournaments':
                    # Need seasons first
                    seasons = scraper.fetch_and_store_seasons()
                    scraper.fetch_and_store_tournaments(seasons)
                elif args.step == 'matches':
                    scraper.fetch_and_store_matches_and_races()
                elif args.step == 'persons':
                    scraper.fetch_and_store_persons()
                
                print(f"✅ Step '{args.step}' completed successfully")
            else:
                # Run complete scrape
                scraper.run_full_scrape_with_progress(tournament_mode=False)
                
    except KeyboardInterrupt:
        print("\n⚠️ Scraping interrupted by user")
        logger.info("Scraping interrupted by user")
    except Exception as e:
        print(f"❌ Scraping failed: {e}")
        logger.error(f"Scraping failed: {e}")
        sys.exit(1)
    finally:
        scraper.close()
        print("🔧 Resources cleaned up")

if __name__ == "__main__":
    main()