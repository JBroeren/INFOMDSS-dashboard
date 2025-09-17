#!/usr/bin/env python3
"""
Time Team Data Scraper - JSON Output Version

A scraper for the Time Team API that:
1. Discovers regattas from the API and writes to JSON files
2. Scrapes regatta data, events, races, and related information to JSON files
3. Fetches missing data for clubs, members, and persons to JSON files
4. Organizes data in a structured directory with persistent volumes

Usage:
    python time_team_scraper.py
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
JSON_OUTPUT_DIR = os.getenv('JSON_OUTPUT_DIR', './data/time_team_data')

LOCALE_FILTER = os.getenv('LOCALE_FILTER', 'Europe/Amsterdam')

class TimeTeamDataScraper:
    """Time Team Data Scraper with JSON Output"""
    
    def __init__(self, max_workers: int = 5):
        self.base_url = "https://api.beta.regatta.time-team.nl/api/1"
        self.max_workers = max_workers
        
        # Setup JSON output directories
        self._setup_output_directories()
        
        # Initialize session
        self.session = self._create_session()
        
        # Track processed items to avoid duplicates
        self.processed_regattas = set()
        self.processed_clubs = set()
        self.processed_members = set()
        
        logger.info(f"Time Team Data Scraper initialized with {max_workers} workers")
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
                self.output_dir = Path('/tmp/time_team_data')
                self.output_dir.mkdir(parents=True, exist_ok=True)
                print(f"⚠️  Using fallback directory: {self.output_dir}")
        
        # Create subdirectories for different data types
        self.dirs = {
            'regattas': self.output_dir / 'regattas',
            'events': self.output_dir / 'events',
            'races': self.output_dir / 'races',
            'entries': self.output_dir / 'entries',
            'finals': self.output_dir / 'finals',
            'rounds': self.output_dir / 'rounds',
            'communications': self.output_dir / 'communications',
            'clubs': self.output_dir / 'clubs',
            'members': self.output_dir / 'members',
            'metadata': self.output_dir / 'metadata',
            'final_results': self.output_dir / 'final_results',
            'race_crews': self.output_dir / 'race_crews',
            'crew_times': self.output_dir / 'crew_times',
            'rankings': self.output_dir / 'rankings'
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
        """Create a requests session with proper headers and proxy support"""
        session = requests.Session()
        session.timeout = 30
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Origin': 'https://beta.regatta.time-team.nl/',
            'Referer': 'https://beta.regatta.time-team.nl/',
        })
        
        # Configure proxy if available
        proxy_url = os.getenv('PROXY_URL')
        if proxy_url:
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

    def fetch_all_regattas(self):
        """Step 1: Always fetch all regattas"""
        print("📅 Fetching all regattas...")
        
        # Fetch all regattas
        regattas_data = self._fetch_json(f"{self.base_url}/regatta")
        
        if not regattas_data:
            print("❌ No regattas found")
            return
        
        regattas = regattas_data.get('regatta', {})
        # regatta is an object with the key being the regatta id and the value being the regatta data
        regattas = list(regattas.values())
        print(f"📅 Found {len(regattas)} regattas")
        
        # Store regattas
        for regatta in regattas:
            regatta_id = self._to_uuid(regatta.get('id'))
            timezone = regatta.get('timezone')
            if regatta_id and timezone == LOCALE_FILTER:
                file_path = self.dirs['regattas'] / f"{regatta_id}.json"
                self._write_json_file(regatta, file_path, {
                    'type': 'regatta',
                    'scanned': False
                })
                # create subdirectories for this regatta in all other directories
                for dir_path in self.dirs.values():
                    dir_path = dir_path / f"{regatta_id}"
                    dir_path.mkdir(parents=True, exist_ok=True)
                
        
        print(f"✅ Stored {len(regattas)} regattas")
        return regattas

    def scrape_unscanned_regattas(self):
        """Step 2: Scrape only unscanned regattas"""
        print("🏆 Scraping unscanned regattas...")
        
        # Get unscanned regattas from JSON files
        regatta_files = list(self.dirs['regattas'].glob('*.json'))
        unscanned_regattas = []
        
        for file_path in regatta_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if not data.get('metadata', {}).get('scanned', False):
                        regatta_id = file_path.stem
                        regatta_data = data['data']
                        unscanned_regattas.append((regatta_id, regatta_data))
            except Exception as e:
                logger.warning(f"Failed to read regatta file {file_path}: {e}")
        
        if not unscanned_regattas:
            print("✅ No unscanned regattas found")
            return
        
        print(f"🏆 Found {len(unscanned_regattas)} unscanned regattas")
        
        def process_regatta(regatta_data):
            """Process a single regatta"""
            regatta_id, regatta = regatta_data
            
            try:
                regatta_name = regatta.get('name', 'Unknown')
                print(f"  Processing regatta: {regatta_name}")

                # check if we already have races, events and/or communication for this regatta:
                races_dir = self.dirs['races'] / f"{regatta_id}"
                events_dir = self.dirs['events'] / f"{regatta_id}"
                communication_dir = self.dirs['communications'] / f"{regatta_id}"

                # Fetch regatta details
                regatta_details = self._fetch_json(f"{self.base_url}/regatta/{regatta_id}")
                if regatta_details:
                    # Update the regatta file with detailed data
                    regatta_file = self.dirs['regattas'] / f"{regatta_id}.json"
                    with open(regatta_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    data['data'] = regatta_details
                    with open(regatta_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

                event_count = 0
                race_count = 0
                comm_count = 0

                # Fetch events
                if not events_dir.exists() or not any(events_dir.iterdir()):
                    events_data = self._fetch_json(f"{self.base_url}/{regatta_id}/event") or []

                    # Store events
                    if len(events_data) > 0:
                        for event in events_data.get('event', {}).values():
                            event_id = self._to_uuid(event.get('id'))
                            if event_id:
                                file_path = self.dirs['events'] / f"{regatta_id}" / f"{event_id}.json"
                                self._write_json_file(event, file_path, {
                                    'type': 'event',
                                    'regatta_id': regatta_id
                                })
                                event_count += 1

                # Fetch races
                if not races_dir.exists() or not any(races_dir.iterdir()):
                    races_data = self._fetch_json(f"{self.base_url}/{regatta_id}/race") or []

                    # Store races
                    if len(races_data) > 0:
                        for race in races_data.get('race', {}).values():
                            race_id = self._to_uuid(race.get('id'))
                            if race_id:
                                file_path = self.dirs['races'] / f"{regatta_id}" / f"{race_id}.json"
                                self._write_json_file(race, file_path, {
                                    'type': 'race',
                                    'regatta_id': regatta_id
                                })
                                race_count += 1
                
                # Fetch communication
                if not communication_dir.exists() or not any(communication_dir.iterdir()):
                    communication_data = self._fetch_json(f"{self.base_url}/{regatta_id}/communication") or []

                    # Store communication
                    if len(communication_data) > 0:
                        for comm in communication_data.get('communication', {}).values():
                            comm_id = self._to_uuid(comm.get('id'))
                            if comm_id:
                                file_path = self.dirs['communications'] / f"{regatta_id}" / f"{comm_id}.json"
                                self._write_json_file(comm, file_path, {
                                    'type': 'communication',
                                    'regatta_id': regatta_id
                                })
                                comm_count += 1           
                    
                # Mark regatta as scanned
                regatta_file = self.dirs['regattas'] / f"{regatta_id}.json"
                with open(regatta_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                data['metadata']['scanned'] = True
                data['metadata']['scanned_at'] = datetime.now().isoformat()
                with open(regatta_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False, default=str)
                
                print(f"    ✅ Stored {event_count} events, {race_count} races, {comm_count} communications")
                return event_count, race_count, comm_count
                    
            except Exception as e:
                logger.warning(f"Failed to process regatta {regatta_name}: {e}")
                return 0, 0, 0
        
        # Process regattas in parallel
        total_events = 0
        total_races = 0
        total_communications = 0
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_regatta = {executor.submit(process_regatta, regatta): regatta for regatta in unscanned_regattas}
            
            for future in as_completed(future_to_regatta):
                events, races, communications = future.result()
                total_events += events
                total_races += races
                total_communications += communications
        
        print(f"✅ Total stored - Events: {total_events}, Races: {total_races}, Communications: {total_communications}")

    def scrape_event_details(self):
        """Step 3: Scrape event details (entries, finals, rounds)"""
        print("🏁 Scraping event details...")
        
        # Get all events from JSON files
        event_files = list(self.dirs['events'].glob('*.json'))
        
        if not event_files:
            print("✅ No events found")
            return
        
        print(f"🏁 Found {len(event_files)} events to process")
        
        def process_event(event_file_path):
            """Process a single event"""
            try:
                with open(event_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    event_data = data['data']
                    event_id = event_file_path.stem
                    regatta_id = data.get('metadata', {}).get('regatta_id')
                
                # Extract original IDs
                original_event_id = event_data.get('id')
                original_regatta_id = event_data.get('metadata', {}).get('regatta_id')
                
                if not original_event_id or not original_regatta_id:
                    return 0, 0, 0
                
                # Fetch event entries
                entries_data = self._fetch_json(f"{self.base_url}/{original_regatta_id}/event/{original_event_id}/entry") or []
                
                # Fetch event finals
                finals_data = self._fetch_json(f"{self.base_url}/{original_regatta_id}/event/{original_event_id}/final")
                
                entry_count = 0
                final_count = 0
                round_count = 0
                
                # Store entries
                for entry in entries_data.get('entry', {}).values():
                    entry_id = self._to_uuid(entry.get('id'))
                    if entry_id:
                        file_path = self.dirs['entries'] / f"{regatta_id}" / f"{entry_id}.json"
                        self._write_json_file(entry, file_path, {
                            'type': 'entry',
                            'event_id': event_id,
                            'regatta_id': regatta_id
                        })
                        entry_count += 1
                
                # Process final results if available
                if finals_data:
                    # Store the main final results data
                    final_id = f"{original_regatta_id}_{original_event_id}"
                    final_results_file = self.dirs['final_results'] / f"{regatta_id}" / f"{final_id}.json"
                    self._write_json_file(finals_data, final_results_file, {
                        'type': 'final_results',
                        'regatta_id': regatta_id,
                        'event_id': event_id,
                        'final_id': final_id
                    })
                    final_count += 1
                    
                    # Extract and store race crew data separately
                    race_crews = finals_data.get('race_crew', {})
                    for crew_id, crew_data in race_crews.items():
                        crew_file = self.dirs['race_crews'] / f"{regatta_id}" / f"{crew_id}.json"
                        self._write_json_file(crew_data, crew_file, {
                            'type': 'race_crew',
                            'regatta_id': regatta_id,
                            'event_id': event_id,
                            'race_id': crew_data.get('race_id'),
                            'crew_id': crew_id
                        })
                        
                        # Store detailed timing data
                        times = crew_data.get('times', [])
                        for time_data in times:
                            time_id = f"{crew_id}_{time_data.get('location_id', 'unknown')}"
                            time_file = self.dirs['crew_times'] / f"{regatta_id}" / f"{time_id}.json"
                            self._write_json_file(time_data, time_file, {
                                'type': 'crew_time',
                                'crew_id': crew_id,
                                'race_id': crew_data.get('race_id'),
                                'regatta_id': regatta_id,
                                'event_id': event_id
                            })
                    
                    # Store ranking data if present
                    event_ranking = finals_data.get('event_ranking', [])
                    
                    if event_ranking:
                        ranking_file = self.dirs['rankings'] / f"{regatta_id}" / f"event_{original_event_id}.json"
                        self._write_json_file(event_ranking, ranking_file, {
                            'type': 'event_ranking',
                            'event_id': original_event_id,
                            'regatta_id': original_regatta_id
                        })
                
                # Process rounds if they exist in the event data
                for round_info in event_data.get('rounds', []):
                    round_id = round_info.get('id')
                    if round_id:
                        round_data = self._fetch_json(f"{self.base_url}/{original_regatta_id}/event/{original_event_id}/round/{round_id}")
                        if round_data:
                            db_round_id = self._to_uuid(round_id)
                            if db_round_id:
                                file_path = self.dirs['rounds'] / f"{regatta_id}" / f"{db_round_id}.json"
                                self._write_json_file(round_data, file_path, {
                                    'type': 'round',
                                    'event_id': event_id,
                                    'regatta_id': regatta_id
                                })
                                round_count += 1
                
                return entry_count, final_count, round_count
                    
            except Exception as e:
                logger.warning(f"Failed to process event {event_file_path}: {e}")
                return 0, 0, 0
        
        # Process events in parallel
        total_entries = 0
        total_finals = 0
        total_rounds = 0
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_event = {executor.submit(process_event, event_file): event_file for event_file in event_files}
            
            for future in as_completed(future_to_event):
                entries, finals, rounds = future.result()
                total_entries += entries
                total_finals += finals
                total_rounds += rounds
        
        print(f"✅ Total stored - Entries: {total_entries}, Finals: {total_finals}, Rounds: {total_rounds}")

    def get_all_rowers_from_final_results(self):
        """Extract and store all rowers from race crews data"""
        print("🚣 Extracting rowers from race crews data...")
        
        race_crews_files = list(self.dirs['race_crews'].glob('*.json'))
        rowers_data = {}
        
        for race_crew_file in race_crews_files:
            try:
                with open(race_crew_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    race_crew_data = data['data']
                    
                    # Process each crew in the race
                    for crew_id, crew_info in race_crew_data.items():
                        entry = crew_info.get('entry', {})
                        rowers = entry.get('rowers', [])
                        
                        # Extract each rower
                        for rower in rowers:
                            rower_id = rower.get('id')
                            if rower_id and rower_id not in rowers_data:
                                rowers_data[rower_id] = {
                                    'id': rower_id,
                                    'firstname': rower.get('firstname'),
                                    'lastname': rower.get('lastname'),
                                    'fullname': rower.get('fullname'),
                                    'club_member_id': rower.get('club_member_id'),
                                    'appearances': []
                                }
                            
                            # Add appearance information
                            if rower_id in rowers_data:
                                appearance = {
                                    'race_id': crew_info.get('race_id'),
                                    'crew_id': crew_id,
                                    'entry_id': crew_info.get('entry_id'),
                                    'position': rower.get('position'),
                                    'club': entry.get('club', {}),
                                    'entry_name': entry.get('name'),
                                    'lane': crew_info.get('lane'),
                                    'status': crew_info.get('status'),
                                    'adjusted_pos': crew_info.get('adjusted_pos'),
                                    'adjusted_result': crew_info.get('adjusted_result')
                                }
                                rowers_data[rower_id]['appearances'].append(appearance)
                        
                        # Also process coxes if present
                        coxes = entry.get('coxes', [])
                        for cox in coxes:
                            cox_id = cox.get('id')
                            if cox_id and cox_id not in rowers_data:
                                rowers_data[cox_id] = {
                                    'id': cox_id,
                                    'firstname': cox.get('firstname'),
                                    'lastname': cox.get('lastname'),
                                    'fullname': cox.get('fullname'),
                                    'club_member_id': cox.get('club_member_id'),
                                    'role': 'cox',
                                    'appearances': []
                                }
                            
                            if cox_id in rowers_data:
                                appearance = {
                                    'race_id': crew_info.get('race_id'),
                                    'crew_id': crew_id,
                                    'entry_id': crew_info.get('entry_id'),
                                    'position': 'cox',
                                    'club': entry.get('club', {}),
                                    'entry_name': entry.get('name'),
                                    'lane': crew_info.get('lane'),
                                    'status': crew_info.get('status'),
                                    'adjusted_pos': crew_info.get('adjusted_pos'),
                                    'adjusted_result': crew_info.get('adjusted_result')
                                }
                                rowers_data[cox_id]['appearances'].append(appearance)
                                
            except Exception as e:
                logger.warning(f"Failed to process race crew file {race_crew_file}: {e}")
                continue
        
        # Create rowers directory if it doesn't exist
        rowers_dir = self.output_dir / 'rowers'
        rowers_dir.mkdir(parents=True, exist_ok=True)
        
        # Store each rower in a separate file
        rower_count = 0
        for rower_id, rower_data in rowers_data.items():
            try:
                rower_uuid = self._to_uuid(rower_id)
                if rower_uuid:
                    file_path = rowers_dir / f"{rower_uuid}.json"
                    self._write_json_file(rower_data, file_path, {
                        'type': 'rower',
                        'rower_id': rower_id,
                        'total_appearances': len(rower_data['appearances'])
                    })
                    rower_count += 1
            except Exception as e:
                logger.warning(f"Failed to store rower {rower_id}: {e}")
                continue
        
        print(f"✅ Extracted and stored {rower_count} unique rowers")
        return rower_count

    def generate_metadata(self):
        """Generate metadata summary of all scraped data"""
        print("📊 Generating metadata summary...")
        
        metadata = {
            'scraped_at': datetime.now().isoformat(),
            'summary': {
                'regattas': len(list(self.dirs['regattas'].glob('*.json'))),
                'events': len(list(self.dirs['events'].glob('*.json'))),
                'races': len(list(self.dirs['races'].glob('*.json'))),
                'entries': len(list(self.dirs['entries'].glob('*.json'))),
                'finals': len(list(self.dirs['finals'].glob('*.json'))),
                'rounds': len(list(self.dirs['rounds'].glob('*.json'))),
                'communications': len(list(self.dirs['communications'].glob('*.json'))),
                'clubs': len(list(self.dirs['clubs'].glob('*.json'))),
                'members': len(list(self.dirs['members'].glob('*.json'))),
                'final_results': len(list(self.dirs['final_results'].glob('*.json'))),
                'race_crews': len(list(self.dirs['race_crews'].glob('*.json'))),
                'crew_times': len(list(self.dirs['crew_times'].glob('*.json'))),
                'rankings': len(list(self.dirs['rankings'].glob('*.json')))
            },
            'directories': {
                'regattas': str(self.dirs['regattas']),
                'events': str(self.dirs['events']),
                'races': str(self.dirs['races']),
                'entries': str(self.dirs['entries']),
                'finals': str(self.dirs['finals']),
                'rounds': str(self.dirs['rounds']),
                'communications': str(self.dirs['communications']),
                'clubs': str(self.dirs['clubs']),
                'members': str(self.dirs['members']),
                'final_results': str(self.dirs['final_results']),
                'race_crews': str(self.dirs['race_crews']),
                'crew_times': str(self.dirs['crew_times']),
                'rankings': str(self.dirs['rankings'])
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
        print("🚀 Starting Time Team data scraping...")
        start_time = datetime.now()
        
        try:
            # Step 1: Always fetch all regattas
            print("\n" + "="*50)
            print("STEP 1: Fetching all regattas")
            print("="*50)
            self.fetch_all_regattas()
            
            # Step 2: Scrape unscanned regattas
            print("\n" + "="*50)
            print("STEP 2: Scraping unscanned regattas")
            print("="*50)
            self.scrape_unscanned_regattas()
            
            # Step 3: Scrape event details
            print("\n" + "="*50)
            print("STEP 3: Scraping event details")
            print("="*50)
            self.scrape_event_details()
            
            # Step 4: Fetch missing club and member data
            print("\n" + "="*50)
            print("STEP 4: Fetching missing club and member data")
            print("="*50)
            self.fetch_missing_club_and_member_data()
            
            # Step 5: Generate metadata
            print("\n" + "="*50)
            print("STEP 5: Generating metadata")
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
    """Main function to run the Time Team scraper"""
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
    max_workers = int(os.getenv('MAX_WORKERS', '8'))
    print(f"🔧 Using {max_workers} workers")

    # Initialize and run scraper
    scraper = TimeTeamDataScraper(max_workers=max_workers)
    
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