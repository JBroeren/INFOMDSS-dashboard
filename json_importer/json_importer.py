#!/usr/bin/env python3
"""
JSON Importer Service

A service that imports JSON files from scrapers into the relational database.
Supports both KNRB and Time Team data.

Usage:
    python json_importer.py [--source knrb|time_team|all]
"""

import os
import sys
import logging
import json
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dotenv import load_dotenv
import argparse
import unicodedata
import re
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from models import (
    KNRBSeason, KNRBTournament, KNRBMatch, KNRBRace, KNRBPerson, KNRBCrew, KNRBRaceResult, KNRBRaceResultTime, KNRBPerson, KNRBCoach, KNRBCox, KNRBRower
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'knrb_dashboard'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'password'),
    'port': os.getenv('DB_PORT', '5432')
}

class JSONKNRBImporter:
    """JSON Importer for converting scraped JSON files to database records"""
    
    def __init__(self):
        # Setup database connection
        self.engine = create_engine(
            f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
        )
        self.Session = sessionmaker(bind=self.engine)
        
        # JSON data directories
        self.knrb_data_dir = Path(os.getenv('KNRB_DATA_DIR', './data/knrb_data'))
        self.time_team_data_dir = Path(os.getenv('TIME_TEAM_DATA_DIR', './data/time_team_data'))
        
        logger.info(f"JSON Importer initialized")
        logger.info(f"KNRB data directory: {self.knrb_data_dir}")
        logger.info(f"Time Team data directory: {self.time_team_data_dir}")

    def _normalize_name(self, name: Optional[str]) -> Optional[str]:
        """Normalize names for matching: lowercase, strip accents and punctuation."""
        if not name:
            return None
        text = unicodedata.normalize('NFKD', name)
        text = ''.join(ch for ch in text if not unicodedata.combining(ch))
        text = text.lower()
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text or None
    
    def _load_json_file(self, file_path: Path) -> Optional[Dict]:
        """Load JSON file and return the data"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load JSON file {file_path}: {e}")
            return None

    def _to_uuid(self, value: Any) -> Optional[UUID]:
        """Convert a value to a UUID if it's not None"""
        if value is None:
            return None
        if isinstance(value, UUID):
            return value
        return UUID(value)
    
    def _to_int(self, value: int | str | uuid.UUID | None) -> Optional[int]:
        """Convert a value to an int if it's not None"""
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            return uuid.UUID(value).int
        if isinstance(value, uuid.UUID):
            return value.int
        raise ValueError(f"Unsupported value type: {type(value)}")

    def _clear_existing_data(self):
        """Clear all existing data from database tables"""
        session = self.Session()
        try:
            # Delete in order from least dependent to most dependent (children first, parents last)
            session.query(KNRBRaceResultTime).delete()
            session.query(KNRBRaceResult).delete()
            session.query(KNRBRower).delete()
            session.query(KNRBCoach).delete()
            session.query(KNRBCox).delete()
            session.query(KNRBCrew).delete()
            session.query(KNRBPerson).delete()
            session.query(KNRBRace).delete()
            session.query(KNRBMatch).delete()
            session.query(KNRBTournament).delete()
            session.query(KNRBSeason).delete()
            session.commit()
            logger.info("Cleared existing data from all tables")
        finally:
            session.close()

    def _import_seasons(self) -> List[str]:
        """Import all seasons and return list of season IDs"""
        knrb_seasons = list(self.knrb_data_dir.glob('seasons/*.json'))
        season_ids = []
        
        logger.info(f"Importing {len(knrb_seasons)} seasons...")
        
        for season_file in knrb_seasons:
            session = self.Session()
            try:
                raw_season_data = self._load_json_file(season_file)
                if not raw_season_data:
                    continue
                    
                season_data = raw_season_data.get('data')
                season_id = season_data.get('id')
                season_year = int(season_data.get('name'))

                # create the season object
                season_object = KNRBSeason(
                    id=season_id,
                    data=season_data,
                    year=season_year
                )
                session.add(season_object)
                session.commit()
                season_ids.append(season_id)
                logger.info(f"Imported season {season_year} (ID: {season_id})")
                
            except Exception as e:
                logger.error(f"Failed to import season from {season_file}: {e}")
                session.rollback()
            finally:
                session.close()
        
        logger.info(f"Completed importing {len(season_ids)} seasons")
        return season_ids

    def _import_tournament(self, tournament_file: Path) -> bool:
        """Import a single tournament"""
        session = self.Session()
        try:
            raw_tournament_data = self._load_json_file(tournament_file)
            if not raw_tournament_data:
                return False
                
            tournament_data = raw_tournament_data.get('data')
            tournament_metadata = raw_tournament_data.get('metadata')
            tournament_id = tournament_data.get('id')
            tournament_name = tournament_data.get('name')
            tournament_type = tournament_metadata.get('tournamentTypeName')
            tournament_first_date = datetime.strptime(tournament_data.get('firstTournamentDate'), '%Y-%m-%dT%H:%M:%S')
            tournament_last_date = datetime.strptime(tournament_data.get('lastTournamentDate'), '%Y-%m-%dT%H:%M:%S')
            tournament_season_id = tournament_data.get('seasonId')

            # create the tournament object
            tournament_object = KNRBTournament(
                id=tournament_id,
                data=tournament_data,
                name=tournament_name,
                first_date=tournament_first_date,
                last_date=tournament_last_date,
                season_id=tournament_season_id,
                type=tournament_type
            )

            session.add(tournament_object)
            session.commit()
            logger.debug(f"Imported tournament {tournament_name} (ID: {tournament_id})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to import tournament from {tournament_file}: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    def _import_match(self, match_file: Path) -> bool:
        """Import a single match"""
        session = self.Session()
        try:
            raw_match_data = self._load_json_file(match_file)
            if not raw_match_data:
                return False
                
            match_data = raw_match_data.get('data')
            match_metadata = raw_match_data.get('metadata')
            match_id = match_data.get('id')
            match_number = match_data.get('number')
            match_tournament_id = self._to_int(match_metadata.get('tournament_id'))
            match_code = match_data.get('code')
            match_name = match_data.get('name')
            match_boat_category_code = match_data.get('matchBoatCategoryCode')
            match_generated_code = match_data.get('matchGeneratedCode')
            match_category_name = match_data.get('matchCategoryName')
            match_boat_category_name = match_data.get('boatCategoryName')
            match_gender_type = match_data.get('genderType')
            match_date = datetime.strptime(match_data.get('date'), '%Y-%m-%dT%H:%M:%S')
            match_cost = match_data.get('tournamentCostGroupPrice')
            match_full_name = match_data.get('matchFullName')
            match_full_name_with_addition = match_data.get('matchFullNameWithAddition')
            match_name_with_addition = match_data.get('matchNameWithAddition')
            match_code_with_addition = match_data.get('matchCodeWithAddition')

            match_object = KNRBMatch(
                id=match_id,
                match_number=match_number,
                tournament_id=match_tournament_id,
                code=match_code,
                name=match_name,
                boat_category_code=match_boat_category_code,
                match_generated_code=match_generated_code,
                match_category_name=match_category_name,
                boat_category_name=match_boat_category_name,
                gender_type=match_gender_type,
                date=match_date,
                cost=match_cost,
                full_name=match_full_name,
                full_name_with_addition=match_full_name_with_addition,
                name_with_addition=match_name_with_addition,
                code_with_addition=match_code_with_addition
            )
            session.add(match_object)
            session.commit()
            logger.debug(f"Imported match {match_name} (ID: {match_id})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to import match from {match_file}: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    def _import_race(self, race_file: Path) -> bool:
        """Import a single race with all its related data"""
        session = self.Session()
        try:
            raw_race_data = self._load_json_file(race_file)
            if not raw_race_data:
                return False
                
            race_data = raw_race_data.get('data')
            race_metadata = raw_race_data.get('metadata')
            
            # Extract race information
            race_id = race_data.get('id')
            race_match_id = race_data.get('matchId')
            race_name = race_data.get('name')
            race_description = race_data.get('description', "")
            race_start_time_str = race_data.get('startTime')
            race_start_time = datetime.strptime(race_start_time_str, '%Y-%m-%dT%H:%M:%S') if race_start_time_str else None
            race_progression_information = race_data.get('progressionInformation', "")
            race_environment_information = race_data.get('environmentInformation', "")
            race_distance = race_data.get('distance')
            race_is_finals_race = race_data.get('isFinalsRace', False)
            
            # Create race object
            race_object = KNRBRace(
                id=race_id,
                match_id=race_match_id,
                name=race_name,
                description=race_description,
                start_time=race_start_time,
                progression_information=race_progression_information,
                environment_information=race_environment_information,
                distance=race_distance,
                is_finals_race=race_is_finals_race
            )
            session.add(race_object)
            session.commit()
            
            # Process race teams (crews)
            race_race_teams = race_data.get('raceTeams', [])
            
            for race_team in race_race_teams:
                team_version = race_team.get('teamVersion', {})
                
                # Only process active teams
                if not team_version.get('isActive', False):
                    continue
                    
                # Extract crew information
                crew_name = team_version.get('matchTeam', {}).get('teamFullName') or team_version.get('matchTeam', {}).get('name', '')
                
                # Create crew
                crew_object = KNRBCrew(
                    race_id=race_id,
                    name=crew_name
                )
                session.add(crew_object)
                session.commit()
                session.flush()  # Get the crew ID
                crew_id = crew_object.id
                
                # Extract race result information
                end_time = race_team.get('endTime')
                # Calculate end_time_string using 448.09 and convert to mm:ss.tt format
                end_time_seconds = end_time
                if end_time_seconds is not None:
                    hours = int(end_time_seconds // 3600)
                    minutes = int((end_time_seconds % 3600) // 60)
                    seconds = end_time_seconds % 60
                    end_time_string = f"{hours:02d}:{minutes:02d}:{seconds:06.2f}"
                else:
                    end_time_string = None
                end_position = race_team.get('endPosition')
                did_not_finish = race_team.get('didNotFinish')
                did_not_start = race_team.get('didNotStart')
                lane = race_team.get('lane')

                # Create race result
                race_result = KNRBRaceResult(
                    race_id=race_id,
                    crew_id=crew_id,
                    final_time=end_time,
                    final_time_string=end_time_string,
                    position=end_position,
                    did_not_finish=did_not_finish,
                    did_not_start=did_not_start,
                    lane=lane
                )
                session.add(race_result)
                session.commit()
                session.flush()  # Get the race result ID
                race_result_id = race_result.id
                
                # Process intermediate times
                race_team_times = race_team.get('raceTeamTimes', [])
                for time_entry in race_team_times:
                    time_value = time_entry.get('time')
                    distance = time_entry.get('distance')
                    position = time_entry.get('position')
                    split_time = time_entry.get('splitTime', 0.0)
                    is_finish_time = distance == race_distance
                    
                    if time_value and distance and position:
                        race_result_time = KNRBRaceResultTime(
                            race_result_id=race_result_id,
                            time=time_value,
                            distance=distance,
                            total_distance=race_distance,  # Use race distance as total
                            split_time=split_time,
                            position=position,
                            is_finish_time=is_finish_time
                        )
                        session.add(race_result_time)

                session.commit()
                session.flush()
                
                # Process team members (persons)
                team_members = team_version.get('teamMembers', [])
                
                for member in team_members:
                    person_data = member.get('person', {})
                    person_id = self._to_uuid(person_data.get('personId'))
                    person_name = person_data.get('fullName')
                    
                    if not person_id or not person_name:
                        continue
                    
                    # get the person json file
                    person_detailed_file = self.knrb_data_dir / f'persons/{person_id}_detailed.json'
                    
                    raw_person_detailed_data = self._load_json_file(person_detailed_file) or {}
                    person_detailed_data = raw_person_detailed_data.get('data') or {}
                    total_sweeping_points = person_detailed_data.get('totalSweepingPoints')
                    total_sculling_points = person_detailed_data.get('totalScullingPoints')
                    year_of_birth = person_detailed_data.get('yearOfBirth')
                    current_rowing_club = person_detailed_data.get('organisationName')
                    rowing_points = person_detailed_data.get('rowingPoints') or []

                    # clear the person detailed data variable
                    del person_detailed_data
                    del raw_person_detailed_data
                    del person_detailed_file
                        
                    # Use PostgreSQL upsert via raw SQL for thread safety
                    # Needed since another thread might be importing the same person
                    session.execute(
                        text("INSERT INTO knrb_persons (id, name, sculling_points_total, sweeping_points_total, year_of_birth, current_rowing_club) VALUES (:id, :name, :sculling_points_total, :sweeping_points_total, :year_of_birth, :current_rowing_club) ON CONFLICT (id) DO NOTHING"),
                        {"id": person_id, "name": person_name, "sculling_points_total": total_sculling_points, "sweeping_points_total": total_sweeping_points, "year_of_birth": year_of_birth, "current_rowing_club": current_rowing_club}
                    )
                    
                    # Determine role and create appropriate relationship
                    is_cox = member.get('isCox', False)
                    is_coach = member.get('isCoach', False)
                    boat_position = member.get('boatPosition')

                    if is_cox:
                        # Create cox relationship
                        cox_object = KNRBCox(
                            crew_id=crew_id,
                            person_id=person_id,
                            name=person_name
                        )
                        session.add(cox_object)
                        
                    elif is_coach:
                        # Create coach relationship
                        coach_object = KNRBCoach(
                            crew_id=crew_id,
                            person_id=person_id,
                            name=person_name
                        )
                        session.add(coach_object)
                        
                    elif boat_position is not None:

                        # calculate the points at time of race
                        patorsculling = 0
                        patorsweeping = 0

                        for point in rowing_points:
                            date_str = point.get('date')
                            if date_str:
                                # Handle fractional seconds by truncating or using fromisoformat
                                if '.' in date_str:
                                    date_str = date_str.split('.')[0]
                                date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S')
                                # if the date is before the race date, add the point to the total points
                                if date < race_start_time:
                                    if point.get('type').lower() == 'sculling':
                                        patorsculling += point.get('point')
                                    elif point.get('type').lower() == 'sweeping':
                                        patorsweeping += point.get('point')
                            else:
                                logger.error(f"No date found for point {point}")
                                if point.get('type').lower() == 'sculling':
                                    patorsculling += point.get('point')
                                elif point.get('type').lower() == 'sweeping':
                                    patorsweeping += point.get('point')

                        rower_object = KNRBRower(
                            crew_id=crew_id,
                            person_id=person_id,
                            name=person_name,
                            position=boat_position,
                            points_at_time_of_race_sculling=patorsculling,
                            points_at_time_of_race_sweeping=patorsweeping
                        )
                        session.add(rower_object)
                        # Create rower relationship (has boat position and is not cox/coach)
                        
                
                session.commit()
                session.flush()

            logger.debug(f"Imported race {race_id} with {len(race_race_teams)} teams")
            return True
            
        except Exception as e:
            logger.error(f"Failed to import race from {race_file}: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    def _import_regatta_data_parallel(self):
        """Import tournaments, matches, and races in parallel"""
        # Get all files
        knrb_tournaments = list(self.knrb_data_dir.glob('tournaments/*.json'))
        knrb_matches = list(self.knrb_data_dir.glob('matches/*.json'))
        knrb_races = list(self.knrb_data_dir.glob('races/*.json'))
        
        total_files = len(knrb_tournaments) + len(knrb_matches) + len(knrb_races)
        logger.info(f"Starting parallel import of regatta data: {len(knrb_tournaments)} tournaments, {len(knrb_matches)} matches, {len(knrb_races)} races")
        
        # Import tournaments first (as matches depend on them)
        logger.info("Importing tournaments...")
        with ThreadPoolExecutor(max_workers=8) as executor:
            tournament_futures = {executor.submit(self._import_tournament, tournament): tournament for tournament in knrb_tournaments}
            
            tournament_success = 0
            for future in as_completed(tournament_futures):
                if future.result():
                    tournament_success += 1
        
        logger.info(f"Completed tournaments: {tournament_success}/{len(knrb_tournaments)} successful")
        
        # Import matches next (as races depend on them)
        logger.info("Importing matches...")
        with ThreadPoolExecutor(max_workers=8) as executor:
            match_futures = {executor.submit(self._import_match, match): match for match in knrb_matches}
            
            match_success = 0
            for future in as_completed(match_futures):
                if future.result():
                    match_success += 1
        
        logger.info(f"Completed matches: {match_success}/{len(knrb_matches)} successful")
        
        # Finally import races with all their detailed data
        logger.info("Importing races...")
        from tqdm import tqdm

        with ThreadPoolExecutor(max_workers=8) as executor:
            race_futures = {executor.submit(self._import_race, race): race for race in knrb_races}
            
            race_success = 0
            for future in tqdm(as_completed(race_futures), total=len(knrb_races), desc="Importing races"):
                if future.result():
                    race_success += 1

        logger.info(f"Completed races: {race_success}/{len(knrb_races)} successful")
        
        total_success = tournament_success + match_success + race_success
        logger.info(f"Parallel regatta import completed: {total_success}/{total_files} files processed successfully")
        
        return total_success == total_files

    def import_knrb_data(self):
        """Import KNRB data: seasons first, then regatta data in parallel"""
        logger.info("Starting KNRB data import...")
        
        # Clear existing data
        self._clear_existing_data()
        
        # Step 1: Import all seasons sequentially
        logger.info("Step 1: Importing seasons...")
        season_ids = self._import_seasons()
        
        if not season_ids:
            logger.error("No seasons imported. Aborting regatta import.")
            return False
        
        # Step 2: Import regatta data (tournaments, matches, races) in parallel
        logger.info("Step 2: Importing regatta data in parallel...")
        success = self._import_regatta_data_parallel()
        
        logger.info(f"KNRB data import completed {'successfully' if success else 'with errors'}")
        return success

class JSONTimeTeamImporter:
    """JSON Importer for converting scraped JSON files to database records"""
    
    def __init__(self):
        # Setup database connection
        self.engine = create_engine(
            f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
        )
        self.Session = sessionmaker(bind=self.engine)

    def import_time_team_data(self):
        """Import Time Team data"""
        logger.info("Starting Time Team data import...")
        pass

def main():
    """Main function"""    
    # Initialize importer
    importer = JSONKNRBImporter()
    
    success = importer.import_knrb_data()
    # importer.import_time_team_data()

    # Show summary
    if success:
        logger.info("\n📊 Import Summary:")
        # summary = importer.get_import_summary()
        # for table_name, count in summary.items():
            # print(f"  - {table_name}: {count:,} records")
        logger.info("\n✅ Import completed successfully!")
    else:
        logger.info("\n❌ Import completed with errors")
        sys.exit(1)

if __name__ == "__main__":
    main()
