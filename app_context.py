from typing import TYPE_CHECKING

# Use TYPE_CHECKING to avoid circular imports for type hints
if TYPE_CHECKING:
    from services.avianart import AvianartService
    from services.racetime import RacetimeService
    from services.discord import DiscordService
    from services.database import DatabaseService
    from services.apscheduler import APSchedulerService

# Global instances of services, this lets us access them anywhere in the application
avianart_service: "AvianartService" = None
racetime_service: "RacetimeService" = None
discord_service: "DiscordService" = None
database_service: "DatabaseService" = None
scheduler_service: "APSchedulerService" = None


def set_services(
    avianart: "AvianartService",
    racetime: "RacetimeService",
    discord: "DiscordService",
    database: "DatabaseService",
    scheduler: "APSchedulerService",
):
    """
    Sets the global service instances.
    This function should be called once at the start of the application.
    """
    global avianart_service, racetime_service, discord_service, database_service, scheduler_service
    avianart_service = avianart
    racetime_service = racetime
    discord_service = discord
    database_service = database
    scheduler_service = scheduler
