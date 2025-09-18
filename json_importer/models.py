"""
SQLAlchemy models for the INFOMDSS Dashboard database
"""

from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, Index, Integer, UniqueConstraint, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()

class KNRBSeason(Base):
    __tablename__ = 'knrb_seasons'
    
    id = Column(Integer, primary_key=True)
    year = Column(Integer, nullable=False)
    data = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    tournaments = relationship("KNRBTournament", back_populates="season")

    # Indexes
    __table_args__ = (
        Index('idx_knrb_seasons_year', 'year'),
        Index('idx_knrb_seasons_created_at', 'created_at'),
    )

class KNRBTournament(Base):
    __tablename__ = 'knrb_tournaments'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(256), nullable=False)
    season_id = Column(Integer, ForeignKey('knrb_seasons.id'), nullable=False)
    first_date = Column(DateTime, nullable=False)
    last_date = Column(DateTime, nullable=False)
    data = Column(JSONB, nullable=False)
    type = Column(String(256), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    season = relationship("KNRBSeason", back_populates="tournaments")
    matches = relationship("KNRBMatch", back_populates="tournament")
    
    # Indexes
    __table_args__ = (
        Index('idx_knrb_tournaments_season_id', 'season_id'),
        Index('idx_knrb_tournaments_name', 'name'),
        Index('idx_knrb_tournaments_first_date', 'first_date'),
        Index('idx_knrb_tournaments_last_date', 'last_date'),
        Index('idx_knrb_tournaments_type', 'type'),
        Index('idx_knrb_tournaments_created_at', 'created_at'),
    )

class KNRBMatch(Base):
    __tablename__ = 'knrb_matches'
    
    id = Column(Integer, primary_key=True)
    match_number = Column(Integer, nullable=False)
    tournament_id = Column(Integer, ForeignKey('knrb_tournaments.id'), nullable=False)
    code = Column(String(32), nullable=False)
    name = Column(String(256), nullable=False)
    boat_category_code = Column(String(32), nullable=False)
    match_generated_code = Column(String(32), nullable=False)
    match_category_name = Column(String(256), nullable=True)
    boat_category_name = Column(String(256), nullable=False)
    gender_type = Column(String(32), nullable=False)
    date = Column(DateTime, nullable=False)
    cost = Column(Float, nullable=True)
    
    full_name = Column(String(512), nullable=False)
    full_name_with_addition = Column(String(512), nullable=False)
    name_with_addition = Column(String(256), nullable=False)
    code_with_addition = Column(String(32), nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    tournament = relationship("KNRBTournament", back_populates="matches")
    races = relationship("KNRBRace", back_populates="match")
    
    # Indexes
    __table_args__ = (
        Index('idx_knrb_matches_tournament_id', 'tournament_id'),
        Index('idx_knrb_matches_code', 'code'),
        Index('idx_knrb_matches_name', 'name'),
        Index('idx_knrb_matches_boat_category_code', 'boat_category_code'),
        Index('idx_knrb_matches_boat_category_name', 'boat_category_name'),
        Index('idx_knrb_matches_gender_type', 'gender_type'),
        Index('idx_knrb_matches_date', 'date'),
        Index('idx_knrb_matches_full_name', 'full_name'),
        Index('idx_knrb_matches_full_name_with_addition', 'full_name_with_addition'),
        Index('idx_knrb_matches_name_with_addition', 'name_with_addition'),
        Index('idx_knrb_matches_code_with_addition', 'code_with_addition'),
        Index('idx_knrb_matches_created_at', 'created_at'),
    )

class KNRBRace(Base):
    __tablename__ = 'knrb_races'
    
    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, ForeignKey('knrb_matches.id'), nullable=False)
    name = Column(String(256), nullable=False)
    description = Column(String(256), nullable=True)
    start_time = Column(DateTime, nullable=False)
    progression_information = Column(String(256), nullable=True)
    environment_information = Column(String(256), nullable=True)
    distance = Column(Integer, nullable=False)
    is_finals_race = Column(Boolean, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    match = relationship("KNRBMatch", back_populates="races")
    crews = relationship("KNRBCrew", back_populates="race")
    race_results = relationship("KNRBRaceResult", back_populates="race")
    
    # Indexes
    __table_args__ = (
        Index('idx_knrb_races_match_id', 'match_id'),
        Index('idx_knrb_races_created_at', 'created_at'),
    )

class KNRBCrew(Base):
    __tablename__ = 'knrb_crews'
    
    id = Column(Integer, primary_key=True)
    race_id = Column(Integer, ForeignKey('knrb_races.id'), nullable=False)
    name = Column(String(256), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    race = relationship("KNRBRace", back_populates="crews")
    race_results = relationship("KNRBRaceResult", back_populates="crew")
    rowers = relationship("KNRBRower", back_populates="crew")
    coaches = relationship("KNRBCoach", back_populates="crew")
    coxes = relationship("KNRBCox", back_populates="crew")

class KNRBRaceResult(Base):
    __tablename__ = 'knrb_race_results'
    
    id = Column(Integer, primary_key=True)
    race_id = Column(Integer, ForeignKey('knrb_races.id'), nullable=False)
    crew_id = Column(Integer, ForeignKey('knrb_crews.id'), nullable=False)
    final_time = Column(Float, nullable=True)
    final_time_string = Column(String(256), nullable=True)
    position = Column(Integer, nullable=True)
    did_not_finish = Column(Boolean, nullable=False)
    did_not_start = Column(Boolean, nullable=False)
    lane = Column(Integer, nullable=True)
    percentage_of_golden_standard = Column(Float, nullable=True)
    absolute_golden_standard = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    race = relationship("KNRBRace", back_populates="race_results")
    crew = relationship("KNRBCrew", back_populates="race_results")
    times = relationship("KNRBRaceResultTime", back_populates="race_result")

class KNRBRaceResultTime(Base):
    __tablename__ = 'knrb_race_result_times'
    
    id = Column(Integer, primary_key=True)
    race_result_id = Column(Integer, ForeignKey('knrb_race_results.id'), nullable=False)
    time = Column(Float, nullable=True)
    distance = Column(Integer, nullable=False)
    total_distance = Column(Integer, nullable=False)
    split_time = Column(Float, nullable=True)
    position = Column(Integer, nullable=True)
    is_finish_time = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    race_result = relationship("KNRBRaceResult", back_populates="times")

    # Indexes
    __table_args__ = (
        Index('idx_knrb_race_result_times_race_result_id', 'race_result_id'),
        Index('idx_knrb_race_result_times_created_at', 'created_at'),
    )

class KNRBPerson(Base):
    __tablename__ = 'knrb_persons'
    
    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(String(256), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    rowers = relationship("KNRBRower", back_populates="person")
    coaches = relationship("KNRBCoach", back_populates="person")
    coxes = relationship("KNRBCox", back_populates="person")

    # Indexes
    __table_args__ = (
        Index('idx_knrb_persons_created_at', 'created_at'),
    )

class KNRBRower(Base):
    __tablename__ = 'knrb_rowers'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    crew_id = Column(Integer, ForeignKey('knrb_crews.id'), nullable=False)
    person_id = Column(UUID(as_uuid=True), ForeignKey('knrb_persons.id'), nullable=False)
    name = Column(String(256), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    crew = relationship("KNRBCrew", back_populates="rowers")
    person = relationship("KNRBPerson", back_populates="rowers")

    # Indexes
    __table_args__ = (
        Index('idx_knrb_rowers_crew_id', 'crew_id'),
        Index('idx_knrb_rowers_person_id', 'person_id'),
        Index('idx_knrb_rowers_created_at', 'created_at'),
    )

class KNRBCoach(Base):
    __tablename__ = 'knrb_coaches'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    crew_id = Column(Integer, ForeignKey('knrb_crews.id'), nullable=False)
    person_id = Column(UUID(as_uuid=True), ForeignKey('knrb_persons.id'), nullable=False)
    name = Column(String(256), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    crew = relationship("KNRBCrew", back_populates="coaches")
    person = relationship("KNRBPerson", back_populates="coaches")

    # Indexes
    __table_args__ = (
        Index('idx_knrb_coaches_crew_id', 'crew_id'),
        Index('idx_knrb_coaches_person_id', 'person_id'),
        Index('idx_knrb_coaches_created_at', 'created_at'),
    )

class KNRBCox(Base):
    __tablename__ = 'knrb_coxes'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    crew_id = Column(Integer, ForeignKey('knrb_crews.id'), nullable=False)
    person_id = Column(UUID(as_uuid=True), ForeignKey('knrb_persons.id'), nullable=False)
    name = Column(String(256), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    crew = relationship("KNRBCrew", back_populates="coxes")
    person = relationship("KNRBPerson", back_populates="coxes")

    # Indexes
    __table_args__ = (
        Index('idx_knrb_coxes_crew_id', 'crew_id'),
        Index('idx_knrb_coxes_person_id', 'person_id'),
        Index('idx_knrb_coxes_created_at', 'created_at'),
    )

# Time Team models
# class TimeTeamRegatta(Base):
#     __tablename__ = 'time_team_regattas'
    
#     id = Column(UUID(as_uuid=True), primary_key=True)
#     regatta_data = Column(JSONB, nullable=False)
#     scanned = Column(Boolean, default=False)
#     created_at = Column(DateTime(timezone=True), server_default=func.now())
#     updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
#     # Relationships
#     events = relationship("TimeTeamEvent", back_populates="regatta")
#     races = relationship("TimeTeamRace", back_populates="regatta")
#     communications = relationship("TimeTeamCommunication", back_populates="regatta")
    
#     # Indexes
#     __table_args__ = (
#         Index('idx_time_team_regattas_scanned', 'scanned'),
#         Index('idx_time_team_regattas_created_at', 'created_at'),
#     )

# class TimeTeamEvent(Base):
#     __tablename__ = 'time_team_events'
    
#     id = Column(UUID(as_uuid=True), primary_key=True)
#     regatta_id = Column(UUID(as_uuid=True), ForeignKey('time_team_regattas.id'), nullable=False)
#     event_data = Column(JSONB, nullable=False)
#     created_at = Column(DateTime(timezone=True), server_default=func.now())
#     updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
#     # Relationships
#     regatta = relationship("TimeTeamRegatta", back_populates="events")
#     entries = relationship("TimeTeamEntry", back_populates="event")
#     finals = relationship("TimeTeamFinal", back_populates="event")
#     rounds = relationship("TimeTeamRound", back_populates="event")
    
#     # Indexes
#     __table_args__ = (
#         Index('idx_time_team_events_regatta_id', 'regatta_id'),
#         Index('idx_time_team_events_created_at', 'created_at'),
#     )

# class TimeTeamRace(Base):
#     __tablename__ = 'time_team_races'
    
#     id = Column(UUID(as_uuid=True), primary_key=True)
#     regatta_id = Column(UUID(as_uuid=True), ForeignKey('time_team_regattas.id'), nullable=False)
#     race_data = Column(JSONB, nullable=False)
#     created_at = Column(DateTime(timezone=True), server_default=func.now())
#     updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
#     # Relationships
#     regatta = relationship("TimeTeamRegatta", back_populates="races")
    
#     # Indexes
#     __table_args__ = (
#         Index('idx_time_team_races_regatta_id', 'regatta_id'),
#         Index('idx_time_team_races_created_at', 'created_at'),
#     )

# class TimeTeamEntry(Base):
#     __tablename__ = 'time_team_entries'
    
#     id = Column(UUID(as_uuid=True), primary_key=True)
#     event_id = Column(UUID(as_uuid=True), ForeignKey('time_team_events.id'), nullable=False)
#     entry_data = Column(JSONB, nullable=False)
#     created_at = Column(DateTime(timezone=True), server_default=func.now())
#     updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
#     # Relationships
#     event = relationship("TimeTeamEvent", back_populates="entries")
    
#     # Indexes
#     __table_args__ = (
#         Index('idx_time_team_entries_event_id', 'event_id'),
#         Index('idx_time_team_entries_created_at', 'created_at'),
#     )

# class TimeTeamFinal(Base):
#     __tablename__ = 'time_team_finals'
    
#     id = Column(UUID(as_uuid=True), primary_key=True)
#     event_id = Column(UUID(as_uuid=True), ForeignKey('time_team_events.id'), nullable=False)
#     final_data = Column(JSONB, nullable=False)
#     created_at = Column(DateTime(timezone=True), server_default=func.now())
#     updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
#     # Relationships
#     event = relationship("TimeTeamEvent", back_populates="finals")
    
#     # Indexes
#     __table_args__ = (
#         Index('idx_time_team_finals_event_id', 'event_id'),
#         Index('idx_time_team_finals_created_at', 'created_at'),
#     )

# class TimeTeamRound(Base):
#     __tablename__ = 'time_team_rounds'
    
#     id = Column(UUID(as_uuid=True), primary_key=True)
#     event_id = Column(UUID(as_uuid=True), ForeignKey('time_team_events.id'), nullable=False)
#     round_data = Column(JSONB, nullable=False)
#     created_at = Column(DateTime(timezone=True), server_default=func.now())
#     updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
#     # Relationships
#     event = relationship("TimeTeamEvent", back_populates="rounds")
    
#     # Indexes
#     __table_args__ = (
#         Index('idx_time_team_rounds_event_id', 'event_id'),
#         Index('idx_time_team_rounds_created_at', 'created_at'),
#     )

# class TimeTeamCommunication(Base):
#     __tablename__ = 'time_team_communications'
    
#     id = Column(UUID(as_uuid=True), primary_key=True)
#     regatta_id = Column(UUID(as_uuid=True), ForeignKey('time_team_regattas.id'), nullable=False)
#     communication_data = Column(JSONB, nullable=False)
#     created_at = Column(DateTime(timezone=True), server_default=func.now())
#     updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
#     # Relationships
#     regatta = relationship("TimeTeamRegatta", back_populates="communications")
    
#     # Indexes
#     __table_args__ = (
#         Index('idx_time_team_communications_regatta_id', 'regatta_id'),
#         Index('idx_time_team_communications_created_at', 'created_at'),
#     )

# class TimeTeamClub(Base):
#     __tablename__ = 'time_team_clubs'
    
#     id = Column(UUID(as_uuid=True), primary_key=True)
#     club_data = Column(JSONB, nullable=False)
#     created_at = Column(DateTime(timezone=True), server_default=func.now())
#     updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
#     # Indexes
#     __table_args__ = (
#         Index('idx_time_team_clubs_created_at', 'created_at'),
#     )

# class TimeTeamMember(Base):
#     __tablename__ = 'time_team_members'
    
#     id = Column(UUID(as_uuid=True), primary_key=True)
#     member_data = Column(JSONB, nullable=False)
#     created_at = Column(DateTime(timezone=True), server_default=func.now())
#     updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
#     # Indexes
#     __table_args__ = (
#         Index('idx_time_team_members_created_at', 'created_at'),
#     )


# Update relationships
KNRBSeason.tournaments = relationship("KNRBTournament", back_populates="season")
