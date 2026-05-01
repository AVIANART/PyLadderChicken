import requests
from logging_config import setup_logging
import logging
from services.avianart import AvianartService
from services.racetime import RacetimeService
from services.apscheduler import APSchedulerService
from services.discord import DiscordService
from services.database import DatabaseService
from services.s3 import S3Service
import services.api as api
from apscheduler.triggers.cron import CronTrigger
from config import import_config
import asyncio
import app_context
import utils.race_utils as race_utils


async def main():
    config = import_config()
    setup_logging(config)

    logger = logging.getLogger("pyladderchicken")
    logger.info("LadderChicken is starting up 🥚...")
    logger.info("Setting up services...")

    avianart = AvianartService(config["avianart_api_url"], config["avianart_api_key"])

    try:
        racetime = RacetimeService(
            config["racetime_category_slug"],
            config["racetime_client_id"],
            config["racetime_client_secret"],
            local_instance=config.get("racetime_local_instance", False),
        )
    except requests.exceptions.ConnectionError as e:
        logger.error(
            "Failed to connect to RaceTime API. Please check your configuration and ensure the RaceTime server is running."
            f" Error: {e}"
        )
        return

    discord = DiscordService(config["discord_token"])
    database = DatabaseService(
        database_user=config["database_user"],
        database_password=config["database_password"],
        database_name=config["database_name"],
        database_url=config["database_url"],
    )
    scheduler = APSchedulerService(
        avianart=avianart, racetime=racetime, discord=discord, database=database
    )
    s3 = S3Service(
        endpoint_url=config["s3_endpoint_url"],
        access_key=config["s3_access_key"],
        secret_key=config["s3_secret_key"],
        bucket_name=config["s3_public_bucket_name"],
    )
    racetime.start()
    discord_task = asyncio.create_task(discord.start_bot())
    api_task = asyncio.create_task(api.main())

    # Store services in the app context for global access
    app_context.set_services(avianart, racetime, discord, database, scheduler, s3)
    await asyncio.sleep(5)

    await race_utils.schedule_future_races()

    # Check each day for any new races that need to be scheduled
    # Run at 00:45 every day, should never fire when there is other work to do
    scheduler.scheduler.add_job(
        race_utils.schedule_future_races,
        CronTrigger(hour="0", minute="45"),
        id="schedule_future_races",
        replace_existing=True,
    )

    logger.info("LadderChicken startup complete 🐔...")

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await discord.stop_bot()
        await racetime.stop()
        await scheduler.scheduler.shutdown()
        print("Shutting down gracefully...")


if __name__ == "__main__":
    asyncio.run(main())
