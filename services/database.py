import functools
import zoneinfo
from sqlalchemy import create_engine
from sqlalchemy.orm import selectinload, Session
import models
import datetime
import schemas
import utils


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
                .filter(models.ScheduledRace.time > utils.estnow())
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
                    < utils.estnow() + datetime.timedelta(minutes=mins_before_start)
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

            all_roles = [role.role for role in roles]
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
                            utils.estnow()
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
                            utils.estnow()
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
                .options(selectinload(models.Race.scheduledRace))
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
        with Session(self.engine) as db:
            db_savior_role = models.SaviorRole(**savior_role.model_dump())
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
