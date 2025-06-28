import asyncio
from functools import partial
import json
from racetime_bot import Bot
import aiohttp

import tenacity


class ExtendedRacetimeBot(Bot):
    """
    Extended Racetime Bot with additional functionality.
    """

    def __init__(self, category_slug, client_id, client_secret, logger):
        self.handler_objects = {}

        super().__init__(category_slug, client_id, client_secret, logger)

        self.logger.info(
            "ExtendedRacetimeBot initialized for category slug: %s", category_slug
        )

    def create_handler(self, race_data):
        """
        Overload the create_handler method to store handler objects.
        The base rt.gg bot only stores the task for the handler, not the handler object itself.
        This lets us retrieve them later to continue using the configured websocket etc. for sending messages.
        """
        handler = super().create_handler(race_data)
        self.handler_objects[race_data.get("name")] = handler
        self.logger.info(f"Handler created and stored for {race_data.get('name')}")
        return handler

    def get_raceroom_url(self, room_name):
        if not room_name.startswith("/"):
            room_name = f"/{room_name}"
        return self.http_uri(f"{room_name}")

    async def start_race(self, **kwargs):
        """
        Open a race room on rt.gg with the provided parameters.
        """

        try:
            async for attempt in tenacity.AsyncRetrying(
                stop=tenacity.stop_after_attempt(10),
                wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
                retry=tenacity.retry_if_exception_type(aiohttp.ClientResponseError),
            ):
                with attempt:
                    self.logger.debug("Attempting to open rt.gg room...")
                    async with aiohttp.request(
                        method="POST",
                        url=self.http_uri(f"/o/{self.category_slug}/startrace"),
                        data=kwargs,
                        headers={"Authorization": f"Bearer {self.access_token}"},
                    ) as response:
                        headers = response.headers
        except tenacity.RetryError as e:
            self.logger.error(
                f"Failed to open rt.gg room after retries: {e} ({e.last_attempt._exception})"
            )
            raise

        if "Location" in headers:
            room = headers["Location"][1:]
            return room

        raise Exception(
            "Failed to open rt.gg room, no Location header found in response."
        )
    
    # Override default refresh to gain access to unlisted rooms
    async def refresh_races(self):
        """
        Retrieve current race information from the category detail API
        endpoint, retrieving the current race list. Creates a handler and task
        for any race that should be handled but currently isn't.

        This method runs in a constant loop, checking for new races every few
        seconds.
        """

        def done(task_name, *args):
            del self.handlers[task_name]

        while True:
            self.logger.info("Refresh races")
            try:
                async with aiohttp.request(
                    method="get",
                    url=self.http_uri(f"/o/{self.category_slug}/data"),
                    raise_for_status=True,
                    headers={"Authorization": f"Bearer {self.access_token}"},
                ) as resp:
                    data = json.loads(await resp.read())
            except Exception:
                self.logger.error(
                    "Fatal error when attempting to retrieve race data.", exc_info=True
                )
                await asyncio.sleep(self.scan_races_every)
                continue
            self.races = {}
            for race in data.get("current_races", []):
                self.races[race.get("name")] = race

            for name, summary_data in self.races.items():
                if name not in self.handlers:
                    try:
                        async with aiohttp.request(
                            method="get",
                            url=self.http_uri(summary_data.get("data_url")),
                            raise_for_status=True,
                            headers={"Authorization": f"Bearer {self.access_token}"},
                        ) as resp:
                            race_data = json.loads(await resp.read())
                    except Exception:
                        self.logger.error(
                            "Fatal error when attempting to retrieve summary data.",
                            exc_info=True,
                        )
                        await asyncio.sleep(self.scan_races_every)
                        continue
                    if self.should_handle(race_data):
                        handler = self.create_handler(race_data)
                        self.handlers[name] = self.loop.create_task(handler.handle())
                        self.handlers[name].add_done_callback(partial(done, name))
                    else:
                        if name in self.state:
                            del self.state[name]
                        self.logger.info(
                            "Ignoring %(race)s by configuration."
                            % {"race": race_data.get("name")}
                        )

            await asyncio.sleep(self.scan_races_every)
