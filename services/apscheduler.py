import datetime
import zoneinfo
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.triggers.date import DateTrigger

from services.avianart import AvianartService
from services.racetime import RacetimeService
from services.discord import DiscordService
from services.database import DatabaseService

import utils


executors = {
    "default": AsyncIOExecutor(),
}

job_defaults = {"coalesce": True, "max_instances": 3}
utc = zoneinfo.ZoneInfo("UTC")
est = zoneinfo.ZoneInfo("US/Eastern")  # Eastern Standard Time (EST) timezone


class ServicesContainer:
    """
    Container for all services used in the application.
    This allows for easy access to services throughout the application.
    """

    def __init__(self, avianart, racetime, discord, database):
        self.avianart: AvianartService = avianart
        self.racetime: RacetimeService = racetime
        self.discord: DiscordService = discord
        self.database: DatabaseService = database


class APSchedulerService:
    """
    Service for managing scheduled jobs using APScheduler.
    This service uses an AsyncIOScheduler with a SQLAlchemy job store.
    """

    def __init__(
        self,
        avianart: AvianartService,
        racetime: RacetimeService,
        discord: DiscordService,
        database: DatabaseService,
    ):
        """
        Initializes the APScheduler service with default job stores, executors, and job defaults.
        """
        self.avianart = avianart
        self.racetime = racetime
        self.discord = discord
        self.database = database
        self.logger = logging.getLogger("SchedulerService")
        self.logger.info("Initializing APSchedulerService...")
        self.scheduler = self.create_scheduler()

        self.scheduler.start()

    def create_scheduler(self):
        """
        Creates and returns an instance of AsyncIOScheduler with configured job stores, executors, and defaults.
        """
        jobstores = {"default": SQLAlchemyJobStore(engine=self.database.engine)}

        scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=utc,
        )
        return scheduler

    def schedule_ladder_race(
        self, race_id=None, immediate=False, open_mins_before_start=30
    ):
        # This will schedule all parts needed for a ladder race to run
        # 1.
        #   a. Open room 30 mins prior to time
        #   b. Ping roles in discord and update schedule with room link
        # 2
        #   a. Roll seed 10 mins prior to time
        #   b. If only one player present, ping @fairy or @potion
        # 3. Ping @unready in rt.gg 1 minute before start
        # 4. Force start the race at time
        # VOD checking will be scheduled separately

        race = self.database.get_scheduled_race_by_id(race_id)

        # Race time is in EST, so we need to first label it as EST and then convert it to UTC
        race_utc_datetime = race.time.replace(tzinfo=est).astimezone(utc)

        self.logger.info(f"Scheduling ladder race {race.id} at {race_utc_datetime} UTC")

        self.scheduler.add_job(
            utils.open_race_room,
            trigger=DateTrigger(
                race_utc_datetime - datetime.timedelta(minutes=open_mins_before_start),
                timezone=utc,
            ),
            args=(race_id,),
            id=f"open_race_{race_id}",
            replace_existing=True,
            # Allow room to be opened until we 1 min before we try to roll the seed
            misfire_grace_time=int((
                (race_utc_datetime - datetime.timedelta(minutes=11))
                - (
                    race_utc_datetime
                    - datetime.timedelta(minutes=open_mins_before_start)
                )
            ).seconds),
            max_instances=1
        )

        self.scheduler.add_job(
            utils.roll_seed,
            trigger=DateTrigger(
                race_utc_datetime - datetime.timedelta(minutes=10),
                timezone=utc,
            ),
            args=(race_id,),
            id=f"roll_seed_{race_id}",
            replace_existing=True,
            # Allow seed to be rolled until 5 minutes before start
            misfire_grace_time=int((
                (race_utc_datetime - datetime.timedelta(minutes=5))
                - (
                    race_utc_datetime - datetime.timedelta(minutes=10)
                )
            ).seconds),
            max_instances=1
        )

        self.scheduler.add_job(
            utils.ping_unready,
            trigger=DateTrigger(
                race_utc_datetime - datetime.timedelta(minutes=1),
                timezone=utc,
            ),
            args=(race_id,),
            id=f"ping_unready_{race_id}",
            replace_existing=True,
            max_instances=1
        )

        self.scheduler.add_job(
            utils.force_start_race,
            trigger=DateTrigger(
                race_utc_datetime - datetime.timedelta(seconds=15),
                timezone=utc,
            ),
            args=(race_id,),
            id=f"force_start_{race_id}",
            replace_existing=True,
            max_instances=1
        )
