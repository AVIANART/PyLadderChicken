import json
from .racetime_bot_extended import ExtendedRacetimeBot
import logging
from racetime_bot import RaceHandler

WELCOME_MESSAGE = "Welcome to this StepLadder race!"


class LadderRaceHandler(RaceHandler):
    def __init__(self, **kwargs):
        self.self_messages = []
        super().__init__(**kwargs)


    async def chat_history(self, data):
        """
        Handle incoming chat history messages.
        """
        for message in data.get('messages', []):
            self.self_messages.append(message.get('message', ''))
        self.logger.info('[%(race)s] Stored chat history"' % {
            'race': self.data.get('name'),
        })
    
        if WELCOME_MESSAGE not in self.self_messages:
            await self.send_message(WELCOME_MESSAGE)

    async def get_chat_history(self):
        """
        Set the `info_bot` field on the race room's data.
        """
        await self.ws.send(json.dumps({
            'action': 'gethistory',
        }))

        self.logger.info('[%(race)s] Retrieved chat history' % {
            'race': self.data.get('name'),
        })

    async def begin(self):
        await self.get_chat_history()
        self.logger.info(f"LadderRaceHandler started for room: {self.data.get('name')}")


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