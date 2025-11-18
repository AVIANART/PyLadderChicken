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
import app_context as ac


executors = {
    "default": AsyncIOExecutor(),
}

job_defaults = {"coalesce": True, "max_instances": 1}
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

    def schedule_race(
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
        )

        if not race.mode_obj.archetype_obj.ladder:
            self.scheduler.add_job(
                utils.ping_unready,
                trigger=DateTrigger(
                    race_utc_datetime - datetime.timedelta(minutes=1),
                    timezone=utc,
                ),
                args=(race_id,),
                id=f"ping_unready_{race_id}",
                replace_existing=True,
            )

            self.scheduler.add_job(
                utils.force_start_race,
                trigger=DateTrigger(
                    race_utc_datetime - datetime.timedelta(seconds=15),
                    timezone=utc,
                ),
                kwargs={"race_id": race_id},
                id=f"force_start_{race_id}",
                replace_existing=True,
            )
        else:
            self.scheduler.add_job(
                utils.warn_partitioned_race,
                trigger=DateTrigger(
                    race_utc_datetime - datetime.timedelta(minutes=3),
                    timezone=utc,
                ),
                kwargs={"race_id": race_id},
                id=f"warn_partitioned_{race_id}",
                replace_existing=True,
            )

            self.scheduler.add_job(
                utils.force_start_race,
                trigger=DateTrigger(
                    race_utc_datetime - datetime.timedelta(minutes=2),
                    timezone=utc,
                ),
                args=(race_id,),
                id=f"force_start_{race_id}",
                replace_existing=True,
            )

    def delay_race_start(self, race_id, delay_minutes):
        jobs_delayed = 0
        try:
            scheduled_race_id = ac.database_service.get_race_by_id(race_id=race_id).scheduledRace.id
        except Exception as e:
            self.logger.error(f"Error getting scheduled race ID for race {race_id}: {e}")
            return jobs_delayed
        for job in ['ping_unready_', 'force_start_', 'warn_partitioned_']:
            job_id = f"{job}{scheduled_race_id}"
            scheduled_job = self.scheduler.get_job(job_id)
            if scheduled_job:
                new_run_time = scheduled_job.next_run_time + datetime.timedelta(
                    minutes=delay_minutes
                )
                self.logger.info(
                    f"Rescheduling job {job_id} to new time {new_run_time} UTC"
                )
                self.scheduler.reschedule_job(
                    job_id,
                    trigger=DateTrigger(
                        new_run_time,
                        timezone=utc,
                    ),
                )
                ac.discord_service.send_message(
                    content=f"Rescheduled job {job_id} to new time {new_run_time} UTC"
                )
                jobs_delayed += 1
        return jobs_delayed

