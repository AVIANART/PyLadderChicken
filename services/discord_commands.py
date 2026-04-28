import schemas
from services.racetime import LadderRaceHandler
import utils
import zoneinfo
import logging
import lightbulb
import hikari
import app_context as ac
from config import import_config
import datetime

loader = lightbulb.Loader()
est = zoneinfo.ZoneInfo("US/Eastern")

logger = logging.getLogger("discord_commands")

config = import_config()


async def autocomplete_modes(ctx: lightbulb.AutocompleteContext[str]) -> None:
    current_value: str = ctx.focused.value or ""
    modes = ac.database_service.get_modes()

    options = {
        f"[{mode.archetype_obj.name}] {mode.name}": str(mode.id) for mode in modes
    }
    # Filter options based on the current value
    if current_value:
        options = {
            name: value
            for name, value in options.items()
            if current_value.lower() in name.lower()
        }
    # Limit to 25 options, discord limit
    options = dict(list(options.items())[:25])
    await ctx.respond(options)


async def autocomplete_archetypes(ctx: lightbulb.AutocompleteContext[str]) -> None:
    current_value: str = ctx.focused.value or ""
    archetypes = ac.database_service.get_archetypes()

    options = {archetype.name: str(archetype.id) for archetype in archetypes}
    if current_value:
        options = {
            name: value
            for name, value in options.items()
            if current_value.lower() in name.lower()
        }
    options = dict(list(options.items())[:25])
    await ctx.respond(options)


async def autocomplete_races(ctx: lightbulb.AutocompleteContext[str]) -> None:
    current_value: str = ctx.focused.value or ""
    latest_races = ac.database_service.get_latest_races()

    options = {
        f"[{race.scheduledRace.mode_obj.name}] {race.raceRoom} - ID: {race.id}": str(
            race.id
        )
        for race in latest_races
    }
    if current_value:
        options = {
            name: value
            for name, value in options.items()
            if current_value.lower() in name.lower()
        }
    options = dict(list(options.items())[:25])
    await ctx.respond(options)


def _get_option_value(ctx: lightbulb.AutocompleteContext, name: str):
    for option in ctx.interaction.options or []:
        if option.name == name:
            return option.value
        # Handle subcommand-style nested options
        nested = getattr(option, "options", None)
        if nested:
            for sub in nested:
                if sub.name == name:
                    return sub.value
    return None


def _resolve_role_label(guild_id, role_id: str, fallback: str) -> str:
    """Try to look up the live role name from the guild cache; fall back otherwise."""
    try:
        bot = ac.discord_service.bot
        rid_int = int(role_id)
    except (AttributeError, TypeError, ValueError):
        return fallback or role_id

    role = None
    if guild_id is not None:
        try:
            role = bot.cache.get_role(rid_int)
        except Exception:
            role = None
        if role is None:
            try:
                roles = bot.cache.get_roles_view_for_guild(guild_id)
                role = roles.get(rid_int) if roles else None
            except Exception:
                role = None
    if role is not None and getattr(role, "name", None):
        return role.name
    return fallback or role_id


async def autocomplete_archetype_pingable_roles(
    ctx: lightbulb.AutocompleteContext[str],
) -> None:
    current_value: str = ctx.focused.value or ""
    archetype_id = _get_option_value(ctx, "archetype")
    options: dict[str, str] = {}
    if archetype_id is not None:
        try:
            archetype_id_int = int(archetype_id)
        except (TypeError, ValueError):
            archetype_id_int = None
        if archetype_id_int is not None:
            pingable_roles = ac.database_service.get_pingable_archetype_roles(
                archetype_id_int
            )
            guild_id = getattr(ctx.interaction, "guild_id", None)
            options = {
                f"{_resolve_role_label(guild_id, pr.roleId, pr.role.roleName)} ({pr.roleId})": pr.roleId
                for pr in pingable_roles
            }
    if current_value:
        options = {
            name: value
            for name, value in options.items()
            if current_value.lower() in name.lower()
            or current_value.lower() in value.lower()
        }
    options = dict(list(options.items())[:25])
    await ctx.respond(options)


async def autocomplete_mode_pingable_roles(
    ctx: lightbulb.AutocompleteContext[str],
) -> None:
    current_value: str = ctx.focused.value or ""
    mode_id = _get_option_value(ctx, "mode")
    options: dict[str, str] = {}
    if mode_id is not None:
        try:
            mode_id_int = int(mode_id)
        except (TypeError, ValueError):
            mode_id_int = None
        if mode_id_int is not None:
            pingable_roles = ac.database_service.get_pingable_mode_roles(mode_id_int)
            guild_id = getattr(ctx.interaction, "guild_id", None)
            options = {
                f"{_resolve_role_label(guild_id, pr.roleId, pr.role.roleName)} ({pr.roleId})": pr.roleId
                for pr in pingable_roles
            }
    if current_value:
        options = {
            name: value
            for name, value in options.items()
            if current_value.lower() in name.lower()
            or current_value.lower() in value.lower()
        }
    options = dict(list(options.items())[:25])
    await ctx.respond(options)


@loader.command()
class OpenRoomCommand(
    lightbulb.SlashCommand,
    name="open_room",
    description="Open a room for a specific race ID.",
    default_member_permissions=hikari.Permissions.NONE,
):
    race_id = lightbulb.integer(
        "race_id",
        "The ID of the race to open the room for.",
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        room = await utils.open_race_room(race_id=ctx.options[0].value)
        if room:
            await ctx.respond(f"Room opened for race {ctx.options[0].value}: {room}")
        else:
            await ctx.respond("Failed to open room. Please check the race ID.")


@loader.command()
class AddScheduledRaceCommand(
    lightbulb.SlashCommand,
    name="add_scheduled_race",
    description="Add a race to the schedule. USE EST TIMEZONE!",
    default_member_permissions=hikari.Permissions.NONE,
):

    mode = lightbulb.integer(
        "mode",
        "The mode of the scheduled race.",
        autocomplete=autocomplete_modes,
    )

    hour = lightbulb.integer(
        "hour",
        "The hour of the scheduled race. Defaults to the next hour.",
        min_value=0,
        max_value=23,
    )
    minute = lightbulb.integer(
        "minute",
        "The minute of the scheduled race. Defaults to 0.",
        default=0,
        min_value=0,
        max_value=59,
    )
    day = lightbulb.integer(
        "day",
        "The day of the scheduled race. Defaults to the current day.",
        default=datetime.datetime.now(tz=est).day,
        min_value=1,
        max_value=31,
    )
    month = lightbulb.integer(
        "month",
        "The month of the scheduled race. Defaults to the current month.",
        default=datetime.datetime.now(tz=est).month,
        min_value=1,
        max_value=12,
    )
    year = lightbulb.integer(
        "year",
        "The year of the scheduled race. Defaults to the current year.",
        default=datetime.datetime.now(tz=est).year,
        min_value=datetime.datetime.now(tz=est).year,
        max_value=datetime.datetime.now(tz=est).year + 2,
    )
    mins_before_start = lightbulb.integer(
        "mins_before_start",
        "The number of minutes before the race to open the room. Defaults to 30.",
        default=30,
        min_value=12,
        max_value=60,
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        results = {
            "hour": datetime.datetime.now(tz=est).hour + 1,
            "minute": 0,
            "day": datetime.datetime.now(tz=est).day,
            "month": datetime.datetime.now(tz=est).month,
            "year": datetime.datetime.now(tz=est).year,
            "mode": "None",
            "mins_before_start": 30,
        }

        for option in ctx.interaction.options:
            results[option.name] = option.value

        dt = datetime.datetime(
            year=results["year"],
            month=results["month"],
            day=results["day"],
            hour=results["hour"],
            minute=results["minute"],
            tzinfo=est,
        )
        new_race = schemas.ScheduledRaceWrite(
            time=dt,
            season=1,  # TODO: Make this dynamic
            mode=results["mode"],
        )
        new_race = ac.database_service.add_race_to_schedule(new_race)

        ac.scheduler_service.schedule_race(
            new_race.id, open_mins_before_start=results["mins_before_start"]
        )
        modes = {mode.id: mode.name for mode in ac.database_service.get_modes()}

        await ctx.respond(
            f"Adding scheduled race {modes.get(results['mode'], 'Unknown')} at {results['year']}-{results['month']:02d}-{results['day']:02d} {results['hour']:02d}:{results['minute']:02d}:00 EST (room will open {results['mins_before_start']} minutes before start time).",
        )


# This is temporary until we set up rt.gg authentication and link discord accounts to rt.gg account
@loader.command()
class SetPostRaceChannelCommand(
    lightbulb.SlashCommand,
    name="set_postrace_channel",
    description="Set the channel to send post-race updates.",
):
    channel = lightbulb.channel(
        "channel",
        "The channel to send post-race updates.",
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        results = {
            "channel": None,
        }

        for option in ctx.interaction.options:
            results[option.name] = option.value

        ac.database_service.set_setting("post_race_channel_id", results["channel"])
        await ctx.respond(f"Set post-race channel to <#{results['channel']}>.")


@loader.command()
class SetRacesChannelCommand(
    lightbulb.SlashCommand,
    name="set_races_channel",
    description="Set the channel to send race updates.",
):
    channel = lightbulb.channel(
        "channel",
        "The channel to send race updates.",
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        results = {
            "channel": None,
        }

        for option in ctx.interaction.options:
            results[option.name] = option.value

        ac.database_service.set_setting("races_channel_id", results["channel"])
        await ctx.respond(f"Set races channel to <#{results['channel']}>.")


@loader.command()
class SetBotLoggingChannelCommand(
    lightbulb.SlashCommand,
    name="set_bot_logging_channel",
    description="Set the channel to send bot logs.",
):
    channel = lightbulb.channel(
        "channel",
        "The channel to send bot logs.",
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        results = {
            "channel": None,
        }

        for option in ctx.interaction.options:
            results[option.name] = option.value

        ac.database_service.set_setting("bot_logging_channel_id", results["channel"])
        await ctx.respond(f"Set bot logging channel to <#{results['channel']}>.")


@loader.command()
class SetAdminRoleCommand(
    lightbulb.SlashCommand,
    name="set_admin_role",
    description="Set the admin role for the bot.",
):
    role = lightbulb.mentionable(
        "role",
        "The role to set as the admin role.",
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        results = {
            "role": None,
        }

        for option in ctx.interaction.options:
            results[option.name] = option.value

        ac.database_service.set_setting("admin_role_id", str(results["role"]))
        await ctx.respond(f"Set admin role to <@&{results['role']}>.")


@loader.command()
class ScheduleCommand(
    lightbulb.SlashCommand,
    name="schedule",
    description="Print the schedule message, will be updated automatically.",
    default_member_permissions=hikari.Permissions.NONE,
):
    num_races = lightbulb.integer(
        "num_races",
        "The number of races to show in the schedule. Defaults to 10.",
        default=10,
        min_value=1,
        max_value=100,
    )

    force_new = lightbulb.boolean(
        "force_new",
        "If true, will create a new schedule message even if one already exists. Defaults to false.",
        default=False,
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        results = {
            "num_races": 10,
            "force_new": False,
        }

        for option in ctx.interaction.options:
            results[option.name] = option.value

        # Do we already have a message for the schedule?
        schedule_message_id = ac.database_service.get_setting("schedule_message_id")
        schedule_channel_id = ac.database_service.get_setting("schedule_channel_id")
        schedule_num_races = ac.database_service.get_setting("schedule_num_races")
        if (
            not schedule_message_id
            or not schedule_channel_id
            or not schedule_num_races
            or results["force_new"]
        ):
            # If not, create a new message
            if schedule_message_id and schedule_channel_id:
                # Delete the old message if it exists
                try:
                    message = await ac.discord_service.bot.rest.fetch_message(
                        channel=schedule_channel_id, message=schedule_message_id
                    )
                    await message.delete()
                except hikari.NotFoundError:
                    logger.warning(
                        f"Schedule message with ID {schedule_message_id} not found in channel {schedule_channel_id}."
                    )

            await ctx.respond("Fetching the scheduled races...")
            schedule_message = await ctx.fetch_response(-1)
            ac.database_service.set_setting("schedule_message_id", schedule_message.id)
            ac.database_service.set_setting(
                "schedule_channel_id", schedule_message.channel_id
            )
            ac.database_service.set_setting("schedule_num_races", results["num_races"])
            schedule_message_id = schedule_message.id
        else:
            # If we do, edit the existing message
            await ctx.respond(
                f"Updating the scheduled races (https://discord.com/channels/{ctx.guild_id}/{schedule_channel_id}/{schedule_message_id}). Use force_new to replace the old message with a new schedule message.",
                ephemeral=True,
            )
        await utils.update_schedule_message()


@loader.command()
class DelayRaceCommand(
    lightbulb.SlashCommand,
    name="delay_race",
    description="Delay the start of a specific race.",
    default_member_permissions=hikari.Permissions.NONE,
):
    race_id = lightbulb.integer(
        "race_id",
        "The ID of the race to delay.",
        autocomplete=autocomplete_races,
    )
    delay_minutes = lightbulb.integer(
        "delay_minutes",
        "The number of minutes to delay the race.",
        min_value=1,
        default=5,
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        results = {i.name: i.value for i in ctx.interaction.options}
        race_id = results["race_id"]
        race = ac.database_service.get_race_by_id(race_id=race_id)
        if not race:
            await ctx.respond(f"Race with ID {race_id} not found.", ephemeral=True)
            return
        race_handler: LadderRaceHandler = ac.racetime_service.handler_objects.get(
            race.raceRoom.lstrip("/"), None
        )
        if not race_handler:
            await ctx.respond(
                f"Race room {race.raceRoom.lstrip('/')} not found. Has it already been closed?",
                ephemeral=True,
            )
            return
        jobs_delayed = ac.scheduler_service.delay_race_start(
            race_id, results["delay_minutes"]
        )
        if jobs_delayed:
            await ctx.respond(f"Delayed {jobs_delayed} jobs for race {race_id}.")
            await race_handler.send_message(
                f'This race has been delayed by {results["delay_minutes"]} minutes.'
            )
        else:
            await ctx.respond(
                f"No jobs found to delay for race {race_id}.", ephemeral=True
            )


@loader.command()
class SetRaceSeedCommand(
    lightbulb.SlashCommand,
    name="set_race_seed",
    description="Set the seed for a specific race. LadderChicken will update the room with the seed.",
    default_member_permissions=hikari.Permissions.NONE,
):
    race_id = lightbulb.integer(
        "race_id",
        "The ID of the race to set the seed for.",
        autocomplete=autocomplete_races,
    )
    seed_hash = lightbulb.string(
        "seed_hash",
        "The seed hash to set for the race from AVIANART (e.g. 'YMrEqPWmG9').",
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        results = {i.name: i.value for i in ctx.interaction.options}
        race_id = results["race_id"]
        seed_hash = results["seed_hash"]
        race = ac.database_service.get_race_by_id(race_id=race_id)
        if not race:
            await ctx.respond(f"Race with ID {race_id} not found.", ephemeral=True)
            return
        await ctx.defer(ephemeral=True)
        race = ac.database_service.get_scheduled_race_by_id(race.scheduledRace.id)
        room_name = ac.database_service.get_race_by_id(race.raceId).raceRoom.lstrip("/")

        seed_info = await ac.avianart_service.fetch_permalink(seed_hash)
        if seed_info.response.status or not seed_info.response.patch:
            await ctx.respond(
                f"Failed to fetch seed with hash {seed_hash}. Please ensure the seed hash is correct and the seed has been generated."
            )
            return

        race_handler: LadderRaceHandler = ac.racetime_service.handler_objects.get(
            room_name, None
        )
        if not race_handler:
            await ctx.respond(
                f"Race room {room_name} not found. Has it already been closed?",
                ephemeral=True,
            )
            return
        hash_str = utils.seed_response_to_hash(seed_info.response)

        await race_handler.send_message(
            f"Here is your seed: https://alttpr.racing/getseed.php?race={race.raceId} - ({hash_str})"
        )
        await race_handler.set_bot_raceinfo(
            f"{race.mode_obj.slug} - https://alttpr.racing/getseed.php?race={race.raceId} - ({hash_str})"
        )
        updated_race = ac.database_service.update_race_seed(
            race.raceId, seed_info.response.hash
        )

        if not updated_race:
            logger.error(
                f"Failed to update race {race.raceId} with seed ID {seed_info.response.hash}."
            )
            admin_role = ac.database_service.get_setting("admin_role_id")
            admin_ping = f"<@&{admin_role}> " if admin_role else ""
            await ac.discord_service.send_message(
                content=f"{admin_ping}Failed to update race {race.raceId} with seed ID {seed_info.response.hash}.",
                force_mention=True,
            )
        await ac.discord_service.send_message(
            content=f"Seed for race {race.raceId}. **Manually set by {ctx.user.username}**: https://avianart.games/perm/{seed_info.response.hash} (https://alttpr.racing/getseed.php?race={race.raceId})",
            suppress_embeds=True,
        )
        await ctx.respond(
            f"Set seed for race {race.raceId} to https://avianart.games/perm/{seed_info.response.hash}."
        )


@loader.command()
class AddSaviorRoleCommand(
    lightbulb.SlashCommand,
    name="set_savior_role",
    description="Set a savior role to an archetype.",
    default_member_permissions=hikari.Permissions.NONE,
):
    archetype = lightbulb.string(
        "archetype",
        "The archetype to set the savior role for.",
        autocomplete=autocomplete_archetypes,
    )
    role = lightbulb.mentionable(
        "role",
        "The role to set as a savior role.",
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        results = {i.name: i.value for i in ctx.interaction.options}
        archetype = ac.database_service.get_archetype_by_id(results["archetype"])
        if archetype.saviorRoles:
            for role in archetype.saviorRoles:
                ac.database_service.delete_savior_role(role.archetypeId, role.roleId)

        if not archetype:
            await ctx.respond("Invalid archetype selected.", ephemeral=True)
            return

        savior_role = schemas.SaviorRoleWrite(
            archetypeId=archetype.id,
            roleId=str(results["role"]),
        )
        role = ac.database_service.add_savior_role(savior_role)
        await ctx.respond(
            f"Set savior role <@&{str(results["role"])}> for {archetype.name}."
        )


@loader.command()
class SetAllSaviorRolesCommand(
    lightbulb.SlashCommand,
    name="set_all_savior_roles",
    description="Set savior roles for all archetypes to the specified role.",
    default_member_permissions=hikari.Permissions.NONE,
):
    role = lightbulb.mentionable(
        "role",
        "The role to set as a savior role for all archetypes.",
    )
    overwrite = lightbulb.boolean(
        "overwrite",
        "If true, will overwrite existing savior roles for all archetypes. Defaults to false.",
        default=False,
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        results = {i.name: i.value for i in ctx.interaction.options}
        role_id = str(results["role"])
        archetypes = ac.database_service.get_archetypes()
        for archetype in archetypes:
            if not results["overwrite"] and archetype.saviorRoles:
                continue
            if archetype.saviorRoles:
                for existing_role in archetype.saviorRoles:
                    ac.database_service.delete_savior_role(
                        existing_role.archetypeId, existing_role.roleId
                    )
            savior_role = schemas.SaviorRoleWrite(
                archetypeId=archetype.id,
                roleId=role_id,
            )
            ac.database_service.add_savior_role(savior_role)
        if results["overwrite"]:
            await ctx.respond(
                f"Overwrote savior roles for all archetypes with <@&{role_id}>."
            )
        else:
            await ctx.respond(
                f"Set savior role <@&{role_id}> for all archetypes without a role."
            )


@loader.command()
class RollSeedCommand(
    lightbulb.SlashCommand,
    name="roll_seed",
    description="Roll a seed from a ladder mode",
):
    mode = lightbulb.string(
        "mode",
        "The mode to roll a seed for.",
        autocomplete=autocomplete_modes,
    )
    race = lightbulb.boolean(
        "race",
        "Whether to roll a race seed.",
        default=False,
    )
    spoiler = lightbulb.boolean(
        "spoiler",
        "Whether to roll as a spoiler seed.",
        default=False,
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        results = {
            "race": self.race,
            "spoiler": self.spoiler,
        }

        for option in ctx.interaction.options:
            results[option.name] = option.value

        mode_id = results["mode"]
        mode = ac.database_service.get_mode_by_id(mode_id)
        if not mode:
            await ctx.respond("Invalid mode selected.", ephemeral=True)
            return
        slug = mode.slug
        namespace = slug.split("/")[0] if "/" in slug else None
        preset = slug.split("/")[1] if "/" in slug else slug
        await ctx.defer(ephemeral=True)
        seed = await ac.avianart_service.generate_seed(
            preset=preset,
            race=results["race"],
            namespace=namespace,
            spoiler=results["spoiler"],
        )
        if results["spoiler"]:
            spoiler_name = utils.avianart_payload_to_spoiler(seed, upload=True)

            await ctx.respond(
                f"""You selected **[{mode.archetype_obj.name}] {mode.name}** ({slug})
Seed: https://avianart.games/perm/{seed.response.hash}. 
Spoiler log: {config['s3_public_bucket_url']}/{spoiler_name}""",
                ephemeral=True,
            )
        else:
            await ctx.respond(
                f"""You selected **[{mode.archetype_obj.name}] {mode.name}** ({slug})
Seed: https://avianart.games/perm/{seed.response.hash}""",
                ephemeral=True,
            )


def _collect_role_ids(results: dict, keys: list[str]) -> list[str]:
    role_ids: list[str] = []
    for key in keys:
        value = results.get(key)
        if value is None:
            continue
        role_id = str(value)
        if role_id not in role_ids:
            role_ids.append(role_id)
    return role_ids


@loader.command()
class AddArchetypeCommand(
    lightbulb.SlashCommand,
    name="add_archetype",
    description="Add a new archetype, optionally with pingable roles.",
    default_member_permissions=hikari.Permissions.NONE,
):
    name = lightbulb.string("name", "The name of the archetype.")
    ladder = lightbulb.boolean(
        "ladder",
        "Whether this archetype is a ladder archetype. Defaults to false.",
        default=False,
    )
    pingable_role_1 = lightbulb.mentionable(
        "pingable_role_1",
        "Optional pingable role for this archetype.",
        default=None,
    )
    pingable_role_2 = lightbulb.mentionable(
        "pingable_role_2",
        "Optional pingable role for this archetype.",
        default=None,
    )
    pingable_role_3 = lightbulb.mentionable(
        "pingable_role_3",
        "Optional pingable role for this archetype.",
        default=None,
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        results = {i.name: i.value for i in ctx.interaction.options}

        archetype = ac.database_service.add_archetype(
            schemas.ArchetypeWrite(
                name=results["name"],
                ladder=bool(results.get("ladder", False)),
            )
        )

        role_ids = _collect_role_ids(
            results, ["pingable_role_1", "pingable_role_2", "pingable_role_3"]
        )
        for role_id in role_ids:
            ac.database_service.add_pingable_archetype_role(
                schemas.PingableArchetypeRoleWrite(
                    archetypeId=archetype.id,
                    roleId=role_id,
                )
            )

        if role_ids:
            mentions = ", ".join(f"<@&{r}>" for r in role_ids)
            await ctx.respond(
                f"Added archetype **{archetype.name}** (ID: {archetype.id}) with pingable roles: {mentions}."
            )
        else:
            await ctx.respond(
                f"Added archetype **{archetype.name}** (ID: {archetype.id})."
            )


@loader.command()
class AddModeCommand(
    lightbulb.SlashCommand,
    name="add_mode",
    description="Add a new mode, optionally with pingable roles.",
    default_member_permissions=hikari.Permissions.NONE,
):
    archetype = lightbulb.integer(
        "archetype",
        "The archetype this mode belongs to.",
        autocomplete=autocomplete_archetypes,
    )
    name = lightbulb.string("name", "The name of the mode.")
    slug = lightbulb.string(
        "slug",
        "The avianart slug for this mode (e.g. 'namespace/preset' or 'preset').",
    )
    description = lightbulb.string(
        "description",
        "Optional description of the mode.",
        default=None,
    )
    pingable_role_1 = lightbulb.mentionable(
        "pingable_role_1",
        "Optional pingable role for this mode.",
        default=None,
    )
    pingable_role_2 = lightbulb.mentionable(
        "pingable_role_2",
        "Optional pingable role for this mode.",
        default=None,
    )
    pingable_role_3 = lightbulb.mentionable(
        "pingable_role_3",
        "Optional pingable role for this mode.",
        default=None,
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        results = {i.name: i.value for i in ctx.interaction.options}

        archetype_id = int(results["archetype"])
        archetype = ac.database_service.get_archetype_by_id(archetype_id)
        if not archetype:
            await ctx.respond("Invalid archetype selected.", ephemeral=True)
            return

        mode = ac.database_service.add_mode(
            schemas.ModeWrite(
                archetype=archetype_id,
                name=results["name"],
                slug=results["slug"],
                description=results.get("description"),
            )
        )

        role_ids = _collect_role_ids(
            results, ["pingable_role_1", "pingable_role_2", "pingable_role_3"]
        )
        for role_id in role_ids:
            ac.database_service.add_pingable_mode_role(
                schemas.PingableModeRoleWrite(
                    modeId=mode.id,
                    roleId=role_id,
                )
            )

        if role_ids:
            mentions = ", ".join(f"<@&{r}>" for r in role_ids)
            await ctx.respond(
                f"Added mode **[{archetype.name}] {mode.name}** (ID: {mode.id}, slug: `{mode.slug}`) with pingable roles: {mentions}."
            )
        else:
            await ctx.respond(
                f"Added mode **[{archetype.name}] {mode.name}** (ID: {mode.id}, slug: `{mode.slug}`)."
            )


@loader.command()
class AddPingableArchetypeRoleCommand(
    lightbulb.SlashCommand,
    name="add_pingable_archetype_role",
    description="Add a pingable role to an archetype.",
    default_member_permissions=hikari.Permissions.NONE,
):
    archetype = lightbulb.integer(
        "archetype",
        "The archetype to add a pingable role to.",
        autocomplete=autocomplete_archetypes,
    )
    role = lightbulb.mentionable(
        "role",
        "The role to add as pingable for this archetype.",
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        results = {i.name: i.value for i in ctx.interaction.options}
        archetype_id = int(results["archetype"])
        archetype = ac.database_service.get_archetype_by_id(archetype_id)
        if not archetype:
            await ctx.respond("Invalid archetype selected.", ephemeral=True)
            return

        role_id = str(results["role"])
        ac.database_service.add_pingable_archetype_role(
            schemas.PingableArchetypeRoleWrite(
                archetypeId=archetype_id,
                roleId=role_id,
            )
        )
        await ctx.respond(
            f"Added pingable role <@&{role_id}> to archetype **{archetype.name}**."
        )


@loader.command()
class AddPingableModeRoleCommand(
    lightbulb.SlashCommand,
    name="add_pingable_mode_role",
    description="Add a pingable role to a mode.",
    default_member_permissions=hikari.Permissions.NONE,
):
    mode = lightbulb.integer(
        "mode",
        "The mode to add a pingable role to.",
        autocomplete=autocomplete_modes,
    )
    role = lightbulb.mentionable(
        "role",
        "The role to add as pingable for this mode.",
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        results = {i.name: i.value for i in ctx.interaction.options}
        mode_id = int(results["mode"])
        mode = ac.database_service.get_mode_by_id(mode_id)
        if not mode:
            await ctx.respond("Invalid mode selected.", ephemeral=True)
            return

        role_id = str(results["role"])
        ac.database_service.add_pingable_mode_role(
            schemas.PingableModeRoleWrite(
                modeId=mode_id,
                roleId=role_id,
            )
        )
        await ctx.respond(
            f"Added pingable role <@&{role_id}> to mode **[{mode.archetype_obj.name}] {mode.name}**."
        )


@loader.command()
class RemovePingableArchetypeRoleCommand(
    lightbulb.SlashCommand,
    name="remove_pingable_archetype_role",
    description="Remove a pingable role from an archetype.",
    default_member_permissions=hikari.Permissions.NONE,
):
    archetype = lightbulb.integer(
        "archetype",
        "The archetype to remove a pingable role from.",
        autocomplete=autocomplete_archetypes,
    )
    role = lightbulb.string(
        "role",
        "The pingable role to remove from this archetype.",
        autocomplete=autocomplete_archetype_pingable_roles,
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        results = {i.name: i.value for i in ctx.interaction.options}
        archetype_id = int(results["archetype"])
        archetype = ac.database_service.get_archetype_by_id(archetype_id)
        if not archetype:
            await ctx.respond("Invalid archetype selected.", ephemeral=True)
            return

        role_id = str(results["role"])
        deleted = ac.database_service.delete_pingable_archetype_role(
            archetype_id, role_id
        )
        if deleted:
            await ctx.respond(
                f"Removed pingable role <@&{role_id}> from archetype **{archetype.name}**."
            )
        else:
            await ctx.respond(
                f"No pingable role <@&{role_id}> found on archetype **{archetype.name}**.",
                ephemeral=True,
            )


@loader.command()
class RemovePingableModeRoleCommand(
    lightbulb.SlashCommand,
    name="remove_pingable_mode_role",
    description="Remove a pingable role from a mode.",
    default_member_permissions=hikari.Permissions.NONE,
):
    mode = lightbulb.integer(
        "mode",
        "The mode to remove a pingable role from.",
        autocomplete=autocomplete_modes,
    )
    role = lightbulb.string(
        "role",
        "The pingable role to remove from this mode.",
        autocomplete=autocomplete_mode_pingable_roles,
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        results = {i.name: i.value for i in ctx.interaction.options}
        mode_id = int(results["mode"])
        mode = ac.database_service.get_mode_by_id(mode_id)
        if not mode:
            await ctx.respond("Invalid mode selected.", ephemeral=True)
            return

        role_id = str(results["role"])
        deleted = ac.database_service.delete_pingable_mode_role(mode_id, role_id)
        if deleted:
            await ctx.respond(
                f"Removed pingable role <@&{role_id}> from mode **[{mode.archetype_obj.name}] {mode.name}**."
            )
        else:
            await ctx.respond(
                f"No pingable role <@&{role_id}> found on mode **[{mode.archetype_obj.name}] {mode.name}**.",
                ephemeral=True,
            )
