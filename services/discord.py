from hikari import GatewayBot, Intents, StartedEvent, MessageCreateEvent, StartingEvent
import app_context as ac
import lightbulb
import logging


class DiscordService:
    def __init__(self, token: str):
        """
        Initializes the Discord service with the provided token.
        """
        self.token = token
        self.bot = GatewayBot(token, intents=Intents.ALL)
        self.client = lightbulb.client_from_app(self.bot)
        self.logger = logging.getLogger("discord")

        self.bot.subscribe(StartingEvent, self.client.start)
        self._register_listeners()

        # TODO: We need to handle persistent messages such as rolling seeds as they become disconnected when the bot restarts.

    def _register_listeners(self):
        """
        Registers event listeners for the Discord bot.
        """

        @self.bot.listen()
        async def on_started(event: StartedEvent):
            self.logger.info(
                f"Discord bot has started! Connected as {self.bot.get_me().username}"
            )

        @self.bot.listen()
        async def on_message_create(event: MessageCreateEvent) -> None:
            if not event.is_human or not event.content:
                return

            me = self.bot.get_me()
            if not me:
                return

            if event.content == f"<@{me.id}> ping":
                await event.message.respond(
                    f"Pong! {self.bot.heartbeat_latency * 1000:.0f}ms."
                )

    async def start_bot(self):
        """
        Starts the Discord bot and connects to the gateway.
        This is an asynchronous method and should be awaited.
        """

        await self.client.load_extensions("services.discord_commands")
        self.logger.info("Loaded Discord commands...")

        if not self.bot.is_alive:
            self.logger.info("Starting Discord bot...")
            await self.bot.start()
        else:
            self.logger.info("Discord bot is already running.")

    async def stop_bot(self):
        """
        Stops the Discord bot gracefully.
        """
        if self.bot.is_alive:
            self.logger.info("Stopping Discord bot...")
            await self.bot.close()
        else:
            self.logger.info("Discord bot is not running.")

    async def send_message(self, content: str, channel_id: int = None):
        """
        Sends a message to a specific channel.

        :param channel_id: The ID of the channel to send the message to.
        :param content: The content of the message to send.

        If no channel ID is provided, it will use the configured bot logging channel ID.
        """
        role_mentions = True
        if not channel_id:
            bot_logging_channel = ac.database_service.get_setting("bot_logging_channel_id")
            role_mentions = False
            if not bot_logging_channel:
                self.logger.error(
                    "No channel ID provided and no update channel configured."
                )
                return
            channel_id = bot_logging_channel
        channel = await self.bot.rest.fetch_channel(channel_id)
        if channel:
            self.logger.info(f"Sending message to channel {channel_id}: {content}")
            await channel.send(content, role_mentions=role_mentions)
        else:
            self.logger.error(f"Channel with ID {channel_id} not found.")
