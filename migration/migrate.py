#!/usr/bin/env python3
"""
PostgreSQL to MongoDB Migration Script for KNRB Data
Migrates relational data structure to document-based MongoDB collections
"""

import psycopg2
import pymongo
from uuid import UUID
import json
from datetime import datetime
import logging
from typing import Dict, List, Any
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class KNRBMigrator:
    def __init__(self, pg_config: Dict[str, str], mongo_config: Dict[str, str]):
        """
        Initialize migrator with database configurations
        
        Args:
            pg_config: PostgreSQL connection parameters
            mongo_config: MongoDB connection parameters
        """
        self.pg_config = pg_config
        self.mongo_config = mongo_config
        self.pg_conn = None
        self.mongo_client = None
        self.mongo_db = None
        
    def connect_databases(self):
        """Establish connections to both databases"""
        try:
            # PostgreSQL connection
            self.pg_conn = psycopg2.connect(**self.pg_config)
            logger.info("Connected to PostgreSQL")
            
            # MongoDB connection
            mongo_url = f"mongodb://{self.mongo_config['host']}:{self.mongo_config['port']}/"
            self.mongo_client = pymongo.MongoClient(mongo_url)
            self.mongo_db = self.mongo_client[self.mongo_config['database']]
            logger.info("Connected to MongoDB")
            
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise
    
    def close_connections(self):
        """Close database connections"""
        if self.pg_conn:
            self.pg_conn.close()
        if self.mongo_client:
            self.mongo_client.close()
        logger.info("Database connections closed")
    
    def convert_row_to_document(self, row: tuple, cursor_description: List) -> Dict[str, Any]:
        """Convert PostgreSQL row to MongoDB document"""
        doc = dict(zip([desc[0] for desc in cursor_description], row))
        
        # Convert UUID id to string and make it _id
        if 'id' in doc and doc['id']:
            doc['_id'] = str(doc.pop('id'))
            
        # Convert foreign key UUIDs to strings
        for key, value in doc.items():
            if key.endswith('_id') and value:
                doc[key] = str(value)
                
        # Handle timestamps
        for key in ['created_at', 'updated_at']:
            if key in doc and doc[key]:
                doc[key] = doc[key]  # Keep as datetime object
                
        return doc
    
    def migrate_simple_table(self, table_name: str, collection_name: str, batch_size: int = 1000):
        """Migrate a simple table to MongoDB collection"""
        logger.info(f"Migrating {table_name} to {collection_name}")
        
        cursor = self.pg_conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name}")
        
        collection = self.mongo_db[collection_name]
        batch = []
        total_migrated = 0
        
        for row in cursor.fetchall():
            doc = self.convert_row_to_document(row, cursor.description)
            batch.append(doc)
            
            if len(batch) >= batch_size:
                collection.insert_many(batch)
                total_migrated += len(batch)
                logger.info(f"Migrated {total_migrated} records from {table_name}")
                batch = []
        
        # Insert remaining records
        if batch:
            collection.insert_many(batch)
            total_migrated += len(batch)
            
        cursor.close()
        logger.info(f"Completed migration of {table_name}: {total_migrated} records")
        return total_migrated
    
    def migrate_races_with_klassementen(self):
        """Migrate races with embedded klassementen and details"""
        logger.info("Migrating races with embedded klassementen")
        
        cursor = self.pg_conn.cursor()
        
        # Complex query to get all related data
        query = """
        SELECT 
            r.id as race_id,
            r.match_id,
            r.race_data,
            r.created_at as race_created_at,
            r.updated_at as race_updated_at,
            k.id as klassement_id,
            k.klassement_data,
            k.created_at as klassement_created_at,
            k.updated_at as klassement_updated_at,
            kd.id as detail_id,
            kd.klassement_detail_data,
            kd.created_at as detail_created_at,
            kd.updated_at as detail_updated_at
        FROM knrb_races r
        LEFT JOIN knrb_klassementen k ON r.id = k.race_id
        LEFT JOIN knrb_klassement_details kd ON k.id = kd.klassement_id
        ORDER BY r.id, k.id, kd.id
        """
        
        cursor.execute(query)
        
        races = {}
        
        for row in cursor.fetchall():
            race_id = str(row[0])
            
            # Initialize race document if not exists
            if race_id not in races:
                races[race_id] = {
                    '_id': race_id,
                    'match_id': str(row[1]) if row[1] else None,
                    'race_data': row[2],
                    'created_at': row[3],
                    'updated_at': row[4],
                    'klassementen': {}
                }
            
            # Add klassement if exists
            if row[5]:  # klassement_id exists
                klassement_id = str(row[5])
                if klassement_id not in races[race_id]['klassementen']:
                    races[race_id]['klassementen'][klassement_id] = {
                        'klassement_id': klassement_id,
                        'klassement_data': row[6],
                        'created_at': row[7],
                        'updated_at': row[8],
                        'details': []
                    }
                
                # Add detail if exists
                if row[9]:  # detail_id exists
                    detail = {
                        'detail_id': str(row[9]),
                        'klassement_detail_data': row[10],
                        'created_at': row[11],
                        'updated_at': row[12]
                    }
                    races[race_id]['klassementen'][klassement_id]['details'].append(detail)
        
        # Convert klassementen dict to list
        for race in races.values():
            race['klassementen'] = list(race['klassementen'].values())
        
        # Insert into MongoDB
        if races:
            self.mongo_db.races.insert_many(list(races.values()))
            logger.info(f"Migrated {len(races)} races with embedded klassementen")
        
        cursor.close()
        return len(races)
    
    def create_indexes(self):
        """Create useful indexes on MongoDB collections"""
        logger.info("Creating indexes on MongoDB collections")
        
        # Tournaments indexes
        self.mongo_db.tournaments.create_index("season_id")
        self.mongo_db.tournaments.create_index("scanned_for_persons")
        
        # Matches indexes
        self.mongo_db.matches.create_index("tournament_id")
        
        # Races indexes
        self.mongo_db.races.create_index("match_id")
        self.mongo_db.races.create_index("klassementen.klassement_id")
        
        # Persons indexes (if needed for searching)
        self.mongo_db.persons.create_index([("person_data", "text")])
        
        logger.info("Indexes created successfully")
    
    def verify_migration(self) -> Dict[str, int]:
        """Verify migration by comparing record counts"""
        logger.info("Verifying migration...")
        
        verification = {}
        
        # Check simple tables
        tables_collections = [
            ('knrb_seasons', 'seasons'),
            ('knrb_tournaments', 'tournaments'), 
            ('knrb_matches', 'matches'),
            ('knrb_persons', 'persons')
        ]
        
        cursor = self.pg_conn.cursor()
        
        for table, collection in tables_collections:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            pg_count = cursor.fetchone()[0]
            
            mongo_count = self.mongo_db[collection].count_documents({})
            
            verification[f"{table} -> {collection}"] = {
                'postgresql': pg_count,
                'mongodb': mongo_count,
                'match': pg_count == mongo_count
            }
        
        # Check races (special case due to embedding)
        cursor.execute("SELECT COUNT(*) FROM knrb_races")
        pg_races_count = cursor.fetchone()[0]
        mongo_races_count = self.mongo_db.races.count_documents({})
        
        verification["knrb_races -> races"] = {
            'postgresql': pg_races_count,
            'mongodb': mongo_races_count,
            'match': pg_races_count == mongo_races_count
        }
        
        cursor.close()
        return verification
    
    def run_migration(self):
        """Execute the complete migration process"""
        try:
            logger.info("Starting KNRB data migration from PostgreSQL to MongoDB")
            
            self.connect_databases()
            
            # Clear existing collections
            logger.info("Clearing existing MongoDB collections")
            collections_to_clear = ['seasons', 'tournaments', 'matches', 'persons', 'races']
            for collection_name in collections_to_clear:
                self.mongo_db[collection_name].delete_many({})
            
            # Migrate simple tables
            migration_results = {}
            migration_results['seasons'] = self.migrate_simple_table('knrb_seasons', 'seasons')
            migration_results['tournaments'] = self.migrate_simple_table('knrb_tournaments', 'tournaments')
            migration_results['matches'] = self.migrate_simple_table('knrb_matches', 'matches')
            migration_results['persons'] = self.migrate_simple_table('knrb_persons', 'persons')
            
            # Migrate races with embedded data
            migration_results['races'] = self.migrate_races_with_klassementen()
            
            # Create indexes
            self.create_indexes()
            
            # Verify migration
            verification = self.verify_migration()
            
            logger.info("Migration completed successfully!")
            logger.info(f"Migration results: {migration_results}")
            
            # Print verification results
            print("\n" + "="*50)
            print("MIGRATION VERIFICATION")
            print("="*50)
            for table_collection, counts in verification.items():
                status = "✓ MATCH" if counts['match'] else "✗ MISMATCH"
                print(f"{table_collection}: PG={counts['postgresql']} | Mongo={counts['mongodb']} | {status}")
            
            return migration_results, verification
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            raise
        finally:
            self.close_connections()


def main():
    # Database configurations
    pg_config = {
        'host': 'db_dashboard',
        'port': 5432,
        'database': 'dashboard',
        'user': 'student',
        'password': 'infomdss'
    }
    
    mongo_config = {
        'host': 'mongo',
        'port': 27017,
        'database': 'knrb_dashboard'
    }
    
    # Run migration
    migrator = KNRBMigrator(pg_config, mongo_config)
    
    try:
        results, verification = migrator.run_migration()
        print("\nMigration completed successfully!")
        return 0
    except Exception as e:
        print(f"Migration failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())