
#!/usr/bin/env python3
"""
KNRB Data Scraper - JSON Output Version

A scraper that:
1. Fetches all tournaments and writes to JSON files
2. Scrapes tournament details (matches, races) and writes to JSON files
3. Fetches user data and writes to JSON files
4. Organizes data in a structured directory with persistent volumes

Usage:
    python knrb_scraper.py
"""

import os
import sys
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import uuid
import time
import json
import requests
from typing import List, Dict, Set, Optional
from threading import Lock
from datetime import datetime
from dotenv import load_dotenv
from contextlib import contextmanager
from pathlib import Path

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# JSON output configuration
JSON_OUTPUT_DIR = os.getenv('JSON_OUTPUT_DIR', './data/knrb_data')

class KNRBDataScraper:
    """KNRB Data Scraper with JSON Output"""
    
    def __init__(self, max_workers: int = 5):
        self.base_url = "https://api.foys.io/tournament/public/api/v1"
        self.federation_id = "348625af-0eff-47b7-80d6-dfa6b5a8ad19"
        self.max_workers = max_workers
        
        # Setup JSON output directories
        self._setup_output_directories()
        
        # Initialize session
        self.session = self._create_session()
        
        # Track processed items to avoid duplicates
        self.processed_tournaments = set()
        self.processed_persons = set()
        
        logger.info(f"KNRB Data Scraper initialized with {max_workers} workers")
        logger.info(f"JSON output directory: {JSON_OUTPUT_DIR}")
    
    def _setup_output_directories(self):
        """Create output directory structure"""
        self.output_dir = Path(JSON_OUTPUT_DIR)
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            # If we can't create the directory, try to create it with broader permissions
            import subprocess
            import os
            try:
                subprocess.run(['mkdir', '-p', str(self.output_dir)], check=True)
                subprocess.run(['chmod', '755', str(self.output_dir)], check=True)
            except Exception:
                # Fallback: create in a writable location
                self.output_dir = Path('/tmp/knrb_data')
                self.output_dir.mkdir(parents=True, exist_ok=True)
                print(f"⚠️  Using fallback directory: {self.output_dir}")
        
        # Create subdirectories for different data types
        self.dirs = {
            'seasons': self.output_dir / 'seasons',
            'tournaments': self.output_dir / 'tournaments',
            'matches': self.output_dir / 'matches',
            'races': self.output_dir / 'races',
            'persons': self.output_dir / 'persons',
            'metadata': self.output_dir / 'metadata'
        }
        
        for dir_path in self.dirs.values():
            dir_path.mkdir(parents=True, exist_ok=True)
        
        print(f"✅ Output directories created at {self.output_dir}")
    
    def _to_uuid(self, value: Optional[object]) -> Optional[uuid.UUID]:
        """Convert various inputs into uuid.UUID"""
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        if isinstance(value, int):
            return uuid.UUID(int=value)
        if isinstance(value, str):
            try:
                return uuid.UUID(value)
            except Exception:
                try:
                    return uuid.UUID(int=int(value))
                except Exception:
                    raise
        raise TypeError(f"Unsupported UUID value type: {type(value)}")

    def _fetch_json(self, url: str, params: Optional[Dict] = None, max_retries: int = 3) -> Optional[object]:
        """Fetch JSON data from URL with retry logic"""
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, params=params, timeout=30)
                if response.status_code == 404:
                    if attempt < max_retries - 1:
                        logger.warning(f"404 error for {url}, retrying... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(1)  # Wait 1 second before retry
                        continue
                    return None
                response.raise_for_status()
                return response.json()
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Failed to fetch {url} (attempt {attempt + 1}/{max_retries}): {e}")
                    time.sleep(1)  # Wait 1 second before retry
                    continue
                logger.warning(f"Failed to fetch {url} after {max_retries} attempts: {e}")
                return None
        return None

    def _write_json_file(self, data: object, file_path: Path, metadata: Optional[Dict] = None):
        """Write data to JSON file with metadata"""
        output_data = {
            'timestamp': datetime.now().isoformat(),
            'data': data
        }
        
        if metadata:
            output_data['metadata'] = metadata
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False, default=str)
    
    def _create_session(self):
        """Create a requests session with proxy support"""
        session = requests.Session()
        session.timeout = 30
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
        })
        
       # Configure proxy if available
        proxy_url = os.getenv('PROXY_URL')

        if not proxy_url:
            raise Exception("PROXY_URL is not set. Do not run the scraper without a proxy.")

        session.proxies = {
            'http': proxy_url,
            'https': proxy_url
        }

        logger.info(f"Using proxy: {proxy_url}")
        # Disable SSL verification when using proxy to avoid certificate issues
        session.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        return session

    def fetch_all_tournaments(self):
        """Step 1: Always fetch all tournaments"""
        print("📅 Fetching all tournaments...")
        
        # First, fetch all seasons
        seasons_data = self._fetch_json(f"{self.base_url}/seasons", params={"federationId": self.federation_id}) or {}
        seasons = seasons_data.get('items', [])
        
        if not seasons:
            print("❌ No seasons found")
            return
        
        print(f"📅 Found {len(seasons)} seasons")
        
        # Store seasons
        for season in seasons:
            season_id = self._to_uuid(season.get('id'))
            if season_id:
                file_path = self.dirs['seasons'] / f"{season_id}.json"
                self._write_json_file(season, file_path, {'type': 'season'})
        
        # Fetch tournaments for all seasons
        all_tournaments = []
        for season in seasons:
            params = {
                'federationId': self.federation_id,
                'seasonId': season['id'],
                'pageSize': 1000,
                'registrationsFilter': False,
                'resultsFilter': True
            }
            tournaments_data = self._fetch_json(f"{self.base_url}/tournaments", params=params) or {}
            tournaments = tournaments_data.get('items', [])
            
            for tournament in tournaments:
                tournament_id = self._to_uuid(tournament.get('id'))
                if tournament_id:
                    file_path = self.dirs['tournaments'] / f"{tournament_id}.json"
                    self._write_json_file(tournament, file_path, {
                        'type': 'tournament',
                        'season_id': season.get('id'),
                        'scanned': False
                    })
                    all_tournaments.append(tournament)
        
        print(f"✅ Stored {len(all_tournaments)} tournaments")
        return all_tournaments

    def scrape_unscanned_tournaments(self):
        """Step 2: Scrape only unscanned tournaments"""
        print("🏆 Scraping unscanned tournaments...")
        
        # Get unscanned tournaments from JSON files
        tournament_files = list(self.dirs['tournaments'].glob('*.json'))
        unscanned_tournaments = []
        
        for file_path in tournament_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if not data.get('metadata', {}).get('scanned', False):
                        tournament_id = file_path.stem
                        tournament_data = data['data']
                        unscanned_tournaments.append((tournament_id, tournament_data))
            except Exception as e:
                logger.warning(f"Failed to read tournament file {file_path}: {e}")
        
        if not unscanned_tournaments:
            print("✅ No unscanned tournaments found")
            return
        
        print(f"🏆 Found {len(unscanned_tournaments)} unscanned tournaments")
        
        def process_tournament(tournament_data):
            """Process a single tournament"""
            tournament_id, tournament = tournament_data
            
            try:
                tournament_name = tournament.get('name', 'Unknown')
                print(f"  Processing tournament: {tournament_name}")
                
                # Fetch matches and races
                params = {
                    'tournamentId': tournament.get('id'),
                    'raceResults': True,
                    'orderByMatchBoatCategoryCodes': True
                }
                matches_data = self._fetch_json(f"{self.base_url}/matches", params=params) or []
                
                match_count = 0
                race_count = 0
                
                for match in matches_data:
                    match_id = self._to_uuid(match.get('id'))
                    if match_id:
                        file_path = self.dirs['matches'] / f"{match_id}.json"
                        self._write_json_file(match, file_path, {
                            'type': 'match',
                            'tournament_id': tournament_id
                        })
                        match_count += 1
                        
                        for race in match.get('races', []):
                            race_id = self._to_uuid(race.get('id'))
                            if race_id:
                                file_path = self.dirs['races'] / f"{race_id}.json"
                                self._write_json_file(race, file_path, {
                                    'type': 'race',
                                    'match_id': str(match_id),
                                    'tournament_id': tournament_id
                                })
                                race_count += 1
                
                # Mark tournament as scanned
                tournament_file = self.dirs['tournaments'] / f"{tournament_id}.json"
                with open(tournament_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                data['metadata']['scanned'] = True
                data['metadata']['scanned_at'] = datetime.now().isoformat()
                with open(tournament_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False, default=str)
                
                print(f"    ✅ Stored {match_count} matches, {race_count} races")
                return match_count, race_count
                    
            except Exception as e:
                logger.warning(f"Failed to process tournament {tournament_name}: {e}")
                return 0, 0
        
        # Process tournaments in parallel
        total_matches = 0
        total_races = 0
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_tournament = {executor.submit(process_tournament, tournament): tournament for tournament in unscanned_tournaments}
            
            for future in as_completed(future_to_tournament):
                matches, races = future.result()
                total_matches += matches
                total_races += races
        
        print(f"✅ Total stored - Matches: {total_matches}, Races: {total_races}")

    def fetch_missing_user_data(self):
        """Step 3: Fetch missing user data for incomplete users"""
        print("👥 Fetching missing user data...")
        
        # Get all persons from race files
        all_persons = []
        race_files = list(self.dirs['races'].glob('*.json'))
        
        for file_path in race_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    race_data = data['data']
                    
                    # Extract persons from race teams
                    for team in race_data.get('raceTeams', []):
                        team_version = team.get('teamVersion', {})
                        for member in team_version.get('teamMembers', []):
                            person = member.get('person')
                            if person and person.get('personId'):
                                all_persons.append(person)
            except Exception as e:
                logger.warning(f"Failed to read race file {file_path}: {e}")
        
        if not all_persons:
            print("✅ No persons found")
            return
        
        print(f"👥 Found {len(all_persons)} persons")
        
        def process_person(person_data):
            """Process a single person"""
            person_id = person_data.get('personId')
            if not person_id or person_id in self.processed_persons:
                return False
            
            self.processed_persons.add(person_id)
            db_person_id = self._to_uuid(person_id)
            
            try:
                # Check if person data already exists
                person_file = self.dirs['persons'] / f"{db_person_id}.json"
                if person_file.exists():
                    return False  # Already exists
                
                # Store basic person data
                self._write_json_file(person_data, person_file, {
                    'type': 'person',
                    'source': 'race_data'
                })
                
                # Fetch detailed person data
                detailed_data = self._fetch_json(f"{self.base_url}/persons/{person_id}")
                if detailed_data:
                    detailed_file = self.dirs['persons'] / f"{db_person_id}_detailed.json"
                    self._write_json_file(detailed_data, detailed_file, {
                        'type': 'person_detailed',
                        'person_id': str(db_person_id)
                    })
                
                # Fetch race overview
                race_overview = self._fetch_json(f"{self.base_url}/races/person-overview-results/{person_id}")
                if race_overview:
                    overview_file = self.dirs['persons'] / f"{db_person_id}_overview.json"
                    self._write_json_file(race_overview, overview_file, {
                        'type': 'person_overview',
                        'person_id': str(db_person_id)
                    })
                
                return True
            except Exception as e:
                logger.warning(f"Failed to process person {person_id}: {e}")
                return False
        
        # Process persons in parallel
        processed_count = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_person = {executor.submit(process_person, person): person for person in all_persons}
            
            for future in as_completed(future_to_person):
                if future.result():
                    processed_count += 1
        
        print(f"✅ Processed {processed_count} persons")

    def generate_metadata(self):
        """Generate metadata summary of all scraped data"""
        print("📊 Generating metadata summary...")
        
        metadata = {
            'scraped_at': datetime.now().isoformat(),
            'summary': {
                'seasons': len(list(self.dirs['seasons'].glob('*.json'))),
                'tournaments': len(list(self.dirs['tournaments'].glob('*.json'))),
                'matches': len(list(self.dirs['matches'].glob('*.json'))),
                'races': len(list(self.dirs['races'].glob('*.json'))),
                'persons': len(list(self.dirs['persons'].glob('*.json')))
            },
            'directories': {
                'seasons': str(self.dirs['seasons']),
                'tournaments': str(self.dirs['tournaments']),
                'matches': str(self.dirs['matches']),
                'races': str(self.dirs['races']),
                'persons': str(self.dirs['persons'])
            }
        }
        
        metadata_file = self.dirs['metadata'] / 'scraping_summary.json'
        self._write_json_file(metadata, metadata_file, {'type': 'metadata'})
        
        print(f"✅ Metadata summary saved to {metadata_file}")
        print(f"📊 Data Summary:")
        for key, value in metadata['summary'].items():
            print(f"  - {key}: {value:,} files")

    def run(self):
        """Run the complete scraping process"""
        print("🚀 Starting KNRB data scraping...")
        start_time = datetime.now()
        
        try:
            # Step 1: Always fetch all tournaments
            print("\n" + "="*50)
            print("STEP 1: Fetching all tournaments")
            print("="*50)
            self.fetch_all_tournaments()
            
            # Step 2: Scrape unscanned tournaments
            print("\n" + "="*50)
            print("STEP 2: Scraping unscanned tournaments")
            print("="*50)
            self.scrape_unscanned_tournaments()
            
            # Step 3: Fetch missing user data
            print("\n" + "="*50)
            print("STEP 3: Fetching missing user data")
            print("="*50)
            self.fetch_missing_user_data()
            
            # Step 4: Generate metadata
            print("\n" + "="*50)
            print("STEP 4: Generating metadata")
            print("="*50)
            self.generate_metadata()
            
            # Final summary
            duration = datetime.now() - start_time
            print("\n" + "="*50)
            print("🎉 SCRAPING COMPLETED SUCCESSFULLY!")
            print("="*50)
            print(f"⏱️ Total duration: {duration}")
            print(f"📁 Data saved to: {self.output_dir}")
                
        except Exception as e:
            print(f"❌ Error during scraping: {e}")
            logger.error(f"Error during scraping: {e}")
            raise
    
    def close(self):
        """Close session"""
        if hasattr(self, 'session'):
            self.session.close()

def main():
    """Main function to run the KNRB scraper"""
    # Check output directory
    output_dir = Path(JSON_OUTPUT_DIR)
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"✅ Created output directory: {output_dir}")
    
    # Proxy found?
    proxy_url = os.getenv('PROXY_URL')
    if proxy_url:
        print(f"🔄 Using proxy: {proxy_url}")
    else:
        print("🔄 No proxy found")

    # Get worker count from environment variable
    max_workers = int(os.getenv('MAX_WORKERS', '10'))
    print(f"🔧 Using {max_workers} workers")

    # Initialize and run scraper
    scraper = KNRBDataScraper(max_workers=max_workers)
    
    try:
        scraper.run()
    except KeyboardInterrupt:
        print("\n⚠️ Scraping interrupted by user")
    except Exception as e:
        print(f"❌ Scraping failed: {e}")
        sys.exit(1)
    finally:
        scraper.close()
        print("🔧 Resources cleaned up")

if __name__ == "__main__":
    main()