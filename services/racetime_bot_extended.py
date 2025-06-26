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
