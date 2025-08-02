import asyncio
import datetime
import json
import zoneinfo

import schemas
import utils
from .racetime_bot_extended import ExtendedRacetimeBot
import logging
from racetime_bot import RaceHandler
import app_context as ac
from apscheduler.triggers.date import DateTrigger


WELCOME_MESSAGE = "Welcome to this StepLadder race!"

utc = zoneinfo.ZoneInfo("UTC")
est = zoneinfo.ZoneInfo("US/Eastern")


class LadderRaceHandler(RaceHandler):
    def __init__(self, **kwargs):
        self.self_messages = []
        self.logger = logging.getLogger("RacetimeRaceHandler")
        self.partitioned_race = None
        super().__init__(**kwargs)

    async def override_stream(self, user_id):
        await self.ws.send(json.dumps({
            "action": "override_stream",
            "data": {
                "user": user_id
            }
        }))

    async def ex_so(self, args, message):
        racers = {x['user']['id']: x for x in self.data['entrants']}
        if message['user']['id'] in racers and not racers[message['user']['id']].get('stream_override', False):
            await self.override_stream(message['user']['id'])
            await ac.discord_service.send_message(
                f"{message['user']['full_name']} ({message['user']['twitch_channel']}) has activated stream override ({ac.racetime_service.get_raceroom_url(self.data.get('name'))})", suppress_embeds=True)


    async def chat_history(self, data):
        """
        Handle incoming chat history messages.
        """
        for message in data.get("messages", []):
            message_text = message.get("message", "")
            self.self_messages.append(message_text)

            # Detect partitioned races
            if message["is_system"] and message_text.startswith(
                "Race partitioned from"
            ):
                self.partitioned_race = message_text


        self.logger.info(
            "[%(race)s] Stored chat history"
            % {
                "race": self.data.get("name"),
            }
        )
        await self.post_begin()

    async def get_chat_history(self):
        """
        Set the `info_bot` field on the race room's data.
        """
        await self.ws.send(
            json.dumps(
                {
                    "action": "gethistory",
                }
            )
        )

        self.logger.info(
            "[%(race)s] Retrieved chat history"
            % {
                "race": self.data.get("name"),
            }
        )

    async def begin(self):
        # Used to detect partitioned races and already messaged rooms
        await self.get_chat_history()
        self.logger.info(f"LadderRaceHandler started for room: {self.data.get('name')}")

    async def post_begin(self):
        """
        Post-processing after the race has begun.
        """
        if WELCOME_MESSAGE not in self.self_messages and self.partitioned_race is None:
            await self.send_message(WELCOME_MESSAGE)

        if self.partitioned_race is not None:
            partitioned_race = ac.database_service.get_partitioned_race_by_room_name(
                self.data.get("name")
            )
            if not partitioned_race:
                self.logger.info("Unhandled partitioned race detected.")
                parent_room = "/" + "/".join(self.partitioned_race.split("/")[-2:])
                parent_race = ac.database_service.get_race_by_room_name(parent_room)
                if parent_race:
                    partitioned_race = schemas.PartitionedRaceWrite(
                        raceId=parent_race.id, raceRoom=self.data.get("name")
                    )
                    partitioned_race = ac.database_service.add_partitioned_race(
                        partitioned_race
                    )
                    partitioned_race = (
                        ac.database_service.get_partitioned_race_by_room_name(
                            self.data.get("name")
                        )
                    )
                else:
                    self.logger.error(
                        f"Failed to find parent race for partitioned race, room {self.data.get('name')}, parent {parent_room}."
                    )
                    return
                await self.send_message(
                    f"@everyone please ready up ASAP, the race will force start on the hour. Failure to do so will result in a DQ."
                )

                scheduled_race = partitioned_race.parentRace.scheduledRace

                race_utc_datetime = (
                    scheduled_race.time.replace(
                        tzinfo=est
                    ).astimezone(utc)
                )

                ac.scheduler_service.scheduler.add_job(
                    utils.force_start_race,
                    trigger=DateTrigger(
                        race_utc_datetime - datetime.timedelta(seconds=15),
                        timezone=utc,
                    ),
                    kwargs={"race_room": self.data.get("name"), "ladder": True, "suppress_post_race_message": True},
                    id=f"force_start_{scheduled_race.raceId}_p{self.data.get('name')}",
                    replace_existing=True,
                )


class RacetimeService(ExtendedRacetimeBot):
    """
    Service for interacting with Racetime.gg.
    """

    def __init__(self, category_slug, client_id, client_secret, local_instance=False):
        bot_logger = logging.getLogger("racetime_bot")
        if local_instance:
            self.racetime_host = "localhost:8000"
            self.racetime_secure = False
        super().__init__(category_slug, client_id, client_secret, bot_logger)

        self.logger.info(
            "RacetimeService initialized with category slug: %s", category_slug
        )

    def get_handler_class(self):
        return LadderRaceHandler

    def start(self):
        """
        Start the Racetime service.
        """
        self.loop.create_task(self.reauthorize())
        self.loop.create_task(self.refresh_races())

    def stop(self):
        """
        Stop the Racetime service.
        """
        self.logger.info("Stopping RacetimeService...")
        self.loop.stop()
