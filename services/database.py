import functools
import zoneinfo
from sqlalchemy import create_engine
from sqlalchemy.orm import selectinload, Session
import models
import datetime
import schemas
import utils.race_utils as race_utils

utc = zoneinfo.ZoneInfo("UTC")
est = zoneinfo.ZoneInfo("US/Eastern")


class DatabaseService:
    def __init__(
        self,
        database_user: str,
        database_password: str,
        database_name: str = "ladder",
        database_url: str = "localhost:3306",
    ):
        self.sqlalchemy_connection_string = f"mysql+pymysql://{database_user}:{database_password}@{database_url}/{database_name}"

        self.engine = create_engine(
            self.sqlalchemy_connection_string, pool_size=512, max_overflow=100
        )
        models.Base.metadata.create_all(self.engine)

    def get_setting(self, key: str):
        with Session(self.engine) as db:
            setting = (
                db.query(models.Setting).filter(models.Setting.name == key).first()
            )
            if setting:
                if setting.type == "int":
                    return int(setting.value)
                elif setting.type == "float":
                    return float(setting.value)
                elif setting.type == "bool":
                    return setting.value.lower() in ("true", "1", "yes")
                return setting.value
            return None

    def set_setting(self, key: str, value: str):
        with Session(self.engine) as db:
            setting = (
                db.query(models.Setting).filter(models.Setting.name == key).first()
            )
            if setting:
                if type(value) == int:
                    setting.value = str(value)
                    setting.type = "int"
                elif type(value) == float:
                    setting.value = str(value)
                    setting.type = "float"
                elif type(value) == bool:
                    setting.value = "true" if value else "false"
                    setting.type = "bool"
                else:
                    setting.value = value
                    setting.type = "str"
            else:
                if type(value) == int:
                    setting = schemas.SettingWrite(
                        name=key, value=str(value), type="int"
                    )
                elif type(value) == float:
                    setting = schemas.SettingWrite(
                        name=key, value=str(value), type="float"
                    )
                elif type(value) == bool:
                    setting = schemas.SettingWrite(
                        name=key, value="true" if value else "false", type="bool"
                    )
                else:
                    setting = schemas.SettingWrite(
                        name=key, value=str(value), type="str"
                    )
                setting = models.Setting(**setting.model_dump())
            db.add(setting)
            db.commit()
            db.refresh(setting)
            return setting

    def add_race_to_schedule(self, scheduled_race: schemas.ScheduledRaceWrite):
        with Session(self.engine) as db:
            db_scheduled_race = models.ScheduledRace(**scheduled_race.model_dump())
            db.add(db_scheduled_race)
            db.commit()
            db.refresh(db_scheduled_race)
            return db_scheduled_race

    def get_scheduled_race_by_id(self, race_id: int):
        with Session(self.engine) as db:
            race = (
                db.query(models.ScheduledRace)
                .options(
                    selectinload(models.ScheduledRace.mode_obj).selectinload(
                        models.Mode.archetype_obj
                    ),
                    selectinload(models.ScheduledRace.race).selectinload(
                        models.Race.rolledMode).selectinload(models.Mode.archetype_obj
                    )
                )
                .filter(models.ScheduledRace.id == race_id)
                .first()
            )
            return race

    def get_next_scheduled_race(self):
        with Session(self.engine) as db:
            next_race = (
                db.query(models.ScheduledRace)
                .options(
                    selectinload(models.ScheduledRace.mode_obj).selectinload(
                        models.Mode.archetype_obj
                    )
                )
                .filter(models.ScheduledRace.time > race_utils.estnow())
                .order_by(models.ScheduledRace.time)
                .first()
            )
            return next_race

    def get_race_by_room_name(self, room_name: str):
        if not room_name.startswith("/"):
            room_name = f"/{room_name}"

        with Session(self.engine) as db:
            race = (
                db.query(models.Race)
                .options(
                    selectinload(models.Race.scheduledRace)
                    .selectinload(models.ScheduledRace.mode_obj)
                    .selectinload(models.Mode.archetype_obj)
                )
                .filter(models.Race.raceRoom == room_name)
                .first()
            )
            return race

    def add_partitioned_race(self, partitioned_race: schemas.PartitionedRaceWrite):
        with Session(self.engine) as db:
            if not partitioned_race.raceRoom.startswith("/"):
                partitioned_race.raceRoom = f"/{partitioned_race.raceRoom}"
            db_partitioned_race = models.PartitionedRace(
                **partitioned_race.model_dump()
            )
            db.add(db_partitioned_race)
            db.commit()
            db.refresh(db_partitioned_race)
            return db_partitioned_race

    def get_partitioned_race_by_room_name(self, room_name: str):
        if not room_name.startswith("/"):
            room_name = f"/{room_name}"
        with Session(self.engine) as db:
            partitioned_race = (
                db.query(models.PartitionedRace)
                .options(
                    selectinload(models.PartitionedRace.parentRace)
                    .selectinload(models.Race.scheduledRace)
                    .selectinload(models.ScheduledRace.mode_obj)
                    .selectinload(models.Mode.archetype_obj)
                )
                .filter(models.PartitionedRace.raceRoom == room_name)
                .first()
            )
            return partitioned_race

    def get_previous_race(self, mins_before_start: int = 30):
        with Session(self.engine) as db:
            previous_race = (
                db.query(models.ScheduledRace)
                .options(
                    selectinload(models.ScheduledRace.mode_obj).selectinload(
                        models.Mode.archetype_obj
                    )
                )
                .filter(
                    models.ScheduledRace.time
                    < race_utils.estnow() + datetime.timedelta(minutes=mins_before_start)
                )
                .order_by(models.ScheduledRace.time.desc())
                .first()
            )
            return previous_race

    def get_default_plus_mode_pingable_roles(self, mode_id: int):
        with Session(self.engine) as db:
            roles = (
                db.query(models.PingableModeRole)
                .options(selectinload(models.PingableModeRole.role))
                .filter(models.PingableModeRole.modeId == mode_id)
                .all()
            )
            default_role = (
                db.query(models.Role).filter(models.Role.roleName == "all").first()
            )

            all_roles = [role.role for role in roles if role.role is not None]
            if default_role and default_role not in all_roles:
                all_roles.append(default_role)
            return all_roles

    def get_archetype_by_id(self, archetype_id: int):
        with Session(self.engine) as db:
            archetype = (
                db.query(models.Archetype)
                .options(
                    selectinload(models.Archetype.saviorRoles).selectinload(
                        models.SaviorRole.role
                    )
                )
                .options(selectinload(models.Archetype.modes))
                .filter(models.Archetype.id == archetype_id)
                .first()
            )
            return archetype

    def get_future_scheduled_races(
        self, mins_before_start: int = 30, limit: int = None
    ):
        with Session(self.engine) as db:
            if limit:
                future_races = (
                    db.query(models.ScheduledRace)
                    .options(
                        selectinload(models.ScheduledRace.mode_obj).selectinload(
                            models.Mode.archetype_obj
                        )
                    )
                    .filter(
                        models.ScheduledRace.time
                        > (
                            race_utils.estnow()
                            + datetime.timedelta(minutes=mins_before_start)
                        )
                    )
                    .limit(limit)
                    .all()
                )
            else:
                future_races = (
                    db.query(models.ScheduledRace)
                    .options(
                        selectinload(models.ScheduledRace.mode_obj).selectinload(
                            models.Mode.archetype_obj
                        )
                    )
                    .filter(
                        models.ScheduledRace.time
                        > (
                            race_utils.estnow()
                            + datetime.timedelta(minutes=mins_before_start)
                        )
                    )
                    .all()
                )
            return future_races

    def add_fired_race(self, race_room: str, scheduled_race: schemas.ScheduledRaceRead):
        with Session(self.engine) as db:
            race = models.Race(
                raceRoom=f"/{race_room}",
                seed="Not_yet_generated",
            )
            db.add(race)
            scheduled_race_update = (
                db.query(models.ScheduledRace)
                .filter(models.ScheduledRace.id == scheduled_race.id)
                .one()
            )

            scheduled_race_update.raceId = race.id
            db.add(scheduled_race_update)
            db.commit()
            return race

    def get_race_by_id(self, race_id: int):
        with Session(self.engine) as db:
            race = (
                db.query(models.Race)
                .options(
                    selectinload(models.Race.scheduledRace),
                    selectinload(models.Race.rolledMode)
                    .selectinload(models.Mode.archetype_obj)
                )
                .filter(models.Race.id == race_id)
                .first()
            )
            return race

    def update_race_seed(self, race_id: int, seed: str):
        with Session(self.engine) as db:
            race = db.query(models.Race).filter(models.Race.id == race_id).first()
            if race:
                race.seed = seed
                db.commit()
                db.refresh(race)
                return race
            return None

    def get_latest_races(self, limit: int = 10):
        with Session(self.engine) as db:
            latest_races = (
                db.query(models.Race)
                .options(
                    selectinload(models.Race.scheduledRace)
                    .selectinload(models.ScheduledRace.mode_obj)
                    .selectinload(models.Mode.archetype_obj)
                )
                .order_by(models.Race.id.desc())
                .limit(limit)
                .all()
            )
            return latest_races

    def add_savior_role(self, savior_role: schemas.SaviorRoleWrite):
        self.get_or_create_role(savior_role.roleId, savior_role.roleName)
        with Session(self.engine) as db:
            db_savior_role = models.SaviorRole(
                **savior_role.model_dump(exclude={"roleName"})
            )
            db.add(db_savior_role)
            db.commit()
            db.refresh(db_savior_role)
            return db_savior_role

    def delete_savior_role(self, archetype_id: int, role_id: str):
        with Session(self.engine) as db:
            savior_role = (
                db.query(models.SaviorRole)
                .filter(
                    models.SaviorRole.archetypeId == archetype_id,
                    models.SaviorRole.roleId == role_id,
                )
                .first()
            )
            if savior_role:
                db.delete(savior_role)
                db.commit()
                return savior_role
            return None

    def get_savior_roles(self, archetype_id: int):
        with Session(self.engine) as db:
            roles = (
                db.query(models.SaviorRole)
                .options(selectinload(models.SaviorRole.role))
                .filter(models.SaviorRole.archetypeId == archetype_id)
                .all()
            )
            return roles

    def get_mode_by_id(self, mode_id: int):
        with Session(self.engine) as db:
            mode = (
                db.query(models.Mode)
                .options(selectinload(models.Mode.archetype_obj))
                .filter(models.Mode.id == mode_id)
                .first()
            )
            return mode

    @functools.cache
    def get_modes(self):
        with Session(self.engine) as db:
            modes = (
                db.query(models.Mode)
                .options(selectinload(models.Mode.archetype_obj))
                .all()
            )
            return modes

    @functools.cache
    def get_archetypes(self):
        with Session(self.engine) as db:
            archetypes = (
                db.query(models.Archetype)
                .options(selectinload(models.Archetype.modes))
                .options(
                    selectinload(models.Archetype.saviorRoles).selectinload(
                        models.SaviorRole.role
                    )
                )
                .all()
            )
            return archetypes

    def add_archetype(self, archetype: schemas.ArchetypeWrite):
        with Session(self.engine) as db:
            db_archetype = models.Archetype(**archetype.model_dump())
            db.add(db_archetype)
            db.commit()
            db.refresh(db_archetype)
            self.get_archetypes.cache_clear()
            return db_archetype

    def add_mode(self, mode: schemas.ModeWrite):
        with Session(self.engine) as db:
            db_mode = models.Mode(**mode.model_dump())
            db.add(db_mode)
            db.commit()
            db.refresh(db_mode)
            self.get_modes.cache_clear()
            self.get_archetypes.cache_clear()
            return db_mode

    def get_or_create_role(self, role_id: str, role_name: str = None):
        with Session(self.engine) as db:
            role = (
                db.query(models.Role)
                .filter(models.Role.roleId == role_id)
                .first()
            )
            if role:
                return role
            role = models.Role(roleId=role_id, roleName=role_name or role_id)
            db.add(role)
            db.commit()
            db.refresh(role)
            return role

    def add_pingable_archetype_role(
        self, pingable_role: schemas.PingableArchetypeRoleWrite
    ):
        self.get_or_create_role(pingable_role.roleId, pingable_role.roleName)
        with Session(self.engine) as db:
            existing = (
                db.query(models.PingableArchetypeRole)
                .filter(
                    models.PingableArchetypeRole.archetypeId
                    == pingable_role.archetypeId,
                    models.PingableArchetypeRole.roleId == pingable_role.roleId,
                )
                .first()
            )
            if existing:
                return existing
            db_pingable = models.PingableArchetypeRole(
                **pingable_role.model_dump(exclude={"roleName"})
            )
            db.add(db_pingable)
            db.commit()
            db.refresh(db_pingable)
            self.get_archetypes.cache_clear()
            return db_pingable

    def add_pingable_mode_role(self, pingable_role: schemas.PingableModeRoleWrite):
        # PingableModeRole.roleId FKs to Role.roleName, so we store the roleName
        # (not the discord snowflake) in the link row's roleId column.
        role = self.get_or_create_role(pingable_role.roleId, pingable_role.roleName)
        link_role_id = role.roleName
        with Session(self.engine) as db:
            existing = (
                db.query(models.PingableModeRole)
                .filter(
                    models.PingableModeRole.modeId == pingable_role.modeId,
                    models.PingableModeRole.roleId == link_role_id,
                )
                .first()
            )
            if existing:
                return existing
            db_pingable = models.PingableModeRole(
                modeId=pingable_role.modeId,
                roleId=link_role_id,
            )
            db.add(db_pingable)
            db.commit()
            db.refresh(db_pingable)
            self.get_modes.cache_clear()
            return db_pingable

    def get_pingable_archetype_roles(self, archetype_id: int):
        with Session(self.engine) as db:
            roles = (
                db.query(models.PingableArchetypeRole)
                .options(selectinload(models.PingableArchetypeRole.role))
                .filter(models.PingableArchetypeRole.archetypeId == archetype_id)
                .all()
            )
            return roles

    def get_pingable_mode_roles(self, mode_id: int):
        with Session(self.engine) as db:
            roles = (
                db.query(models.PingableModeRole)
                .options(selectinload(models.PingableModeRole.role))
                .filter(models.PingableModeRole.modeId == mode_id)
                .all()
            )
            return roles

    def delete_pingable_archetype_role(self, archetype_id: int, role_id: str):
        with Session(self.engine) as db:
            pingable = (
                db.query(models.PingableArchetypeRole)
                .filter(
                    models.PingableArchetypeRole.archetypeId == archetype_id,
                    models.PingableArchetypeRole.roleId == role_id,
                )
                .first()
            )
            if pingable:
                db.delete(pingable)
                db.commit()
                self.get_archetypes.cache_clear()
                return True
            return False

    def delete_pingable_mode_role(self, mode_id: int, role_id: str):
        with Session(self.engine) as db:
            pingable = (
                db.query(models.PingableModeRole)
                .filter(
                    models.PingableModeRole.modeId == mode_id,
                    models.PingableModeRole.roleId == role_id,
                )
                .first()
            )
            if pingable:
                db.delete(pingable)
                db.commit()
                self.get_modes.cache_clear()
                return True
            return False

    def add_spoiler_to_race(self, race_id: int, spoiler_url: str):
        with Session(self.engine) as db:
            race = db.query(models.Race).filter(models.Race.id == race_id).first()
            if race:
                race.spoilerUrl = spoiler_url
                db.commit()
                db.refresh(race)
                return race
            return None
        
    def set_rolled_race_mode(self, race_id: int, mode_id: int):
        with Session(self.engine) as db:
            race = db.query(models.Race).options(
                selectinload(models.Race.rolledMode)
                .selectinload(models.Mode.archetype_obj)
            ).filter(models.Race.id == race_id).first()
            if race:
                race.mode = mode_id
                db.commit()
                db.refresh(race)
                return race
            return None

    def get_seasons_races_by_mode(self, season: int, mode_id: int):
        with Session(self.engine) as db:
            sched_races = (
                db.query(models.ScheduledRace)
                .filter(
                    models.ScheduledRace.season == season,
                    models.ScheduledRace.mode == mode_id,
                )
                .all()
            )
            sched_race_ids = [
                x.raceId for x in sched_races if x.raceId is not None and x.raceId > 0
            ]
            races = (
                db.query(models.Race)
                .options(selectinload(models.Race.rolledMode))
                .filter(models.Race.id.in_(sched_race_ids))
                .all()
            )
            return races
        
    def get_seasons_grabbag_races(self, season: int):
        with Session(self.engine) as db:
            sched_races = (
                db.query(models.ScheduledRace)
                .join(models.ScheduledRace.mode_obj)
                .filter(
                    models.ScheduledRace.season == season,
                    models.Mode.slug == 'ladder/grabbag',
                )
                .all()
            )
            sched_race_ids = [
                x.raceId for x in sched_races if x.raceId is not None and x.raceId > 0
            ]
            races = (
                db.query(models.Race)
                .options(selectinload(models.Race.rolledMode))
                .filter(models.Race.id.in_(sched_race_ids))
                .all()
            )
            return races
        
    def get_grabbag_enabled_modes(self):
        with Session(self.engine) as db:
            modes = (
                db.query(models.Mode)
                .options(selectinload(models.Mode.archetype_obj))
                .filter(models.Mode.grabbag == True)
                .all()
            )
            return modes
        

    def get_current_season(self):
        with Session(self.engine) as db:
            # Get next scheduled race and use its season as current season
            next_race = (
                db.query(models.ScheduledRace)
                .filter(models.ScheduledRace.time > datetime.datetime.now())
                .order_by(models.ScheduledRace.time.asc())
                .first()
            )
            if next_race:
                return next_race.season
            return None
        
    def get_all_races(self):
        with Session(self.engine) as db:
            # Get next scheduled race and use its season as current season
            races = (
                db.query(models.Race)
                .options(
                    selectinload(models.Race.rolledMode).selectinload(
                        models.Mode.archetype_obj
                    )
                ).all()
            )
            return races
        
    def enable_grabbag_for_mode(self, mode_id: int):
        with Session(self.engine) as db:
            mode = db.query(models.Mode).filter(models.Mode.id == mode_id).first()
            if mode:
                mode.grabbag = True
                db.commit()
                db.refresh(mode)
                self.get_modes.cache_clear()
                return mode
            return None
        
    def disable_grabbag_for_mode(self, mode_id: int):
        with Session(self.engine) as db:
            mode = db.query(models.Mode).filter(models.Mode.id == mode_id).first()
            if mode:
                mode.grabbag = False
                db.commit()
                db.refresh(mode)
                self.get_modes.cache_clear()
                return mode
            return None