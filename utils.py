import asyncio
import random
from typing import TYPE_CHECKING
import zoneinfo
import datetime

import datetime
import logging

from services.avianart import AvianResponsePayload
import app_context as ac

if TYPE_CHECKING:
    from services.racetime import LadderRaceHandler


ladder_kwargs = {
    "goal": "Beat the game (Group)",
    "start_delay": 15,
    "time_limit": 6,
    "auto_start": False,
    "allow_midrace_chat": False,
    "allow_non_entrant_chat": True,
    "allow_comments": True,
    "hide_comments": True,
    "streaming_required": True,
    "unlisted": False,
    "chat_message_delay": 0,
    "partitionable": False,
    "hide_entrants": False
}

logger = logging.getLogger("pyladderchicken")

utc = zoneinfo.ZoneInfo("UTC")
est = zoneinfo.ZoneInfo("US/Eastern")

random_post_race_messages = [
    "LOL PED SEED",
    "Nice flute.",
    "Why does StoolChicken hate me?",
    "Anyone else finish without pearl?",
    "15bb...",
    "169, nice.",
    "Always a sword in swamp",
    "LITERAL LAST LOCATION MITTS",
    "Pearl on pyramid, what a surprise.",
    "Hard required fireless IP, finally!",
    "Hover seed smh",
    "Oh course I did X when I should have done Y.",
    "What a rude seed.",
    "Sword go mode sucks.",
    "I should learn glitches..."
]


async def open_race_room(race_id: int):
    """
    Opens a room and notifies the Discord channel.
    """
    race = ac.database_service.get_scheduled_race_by_id(race_id)
    race_utc_datetime = race.time.replace(tzinfo=est).astimezone(utc)
    # Convert from EST to UTC
    delta_ts = (
        datetime.datetime.now(utc) + (race_utc_datetime - datetime.datetime.now(utc))
    ).timestamp()

    ping_roles = ac.database_service.get_default_plus_mode_pingable_roles(
        race.mode_obj.id
    )
    roles_str = ""
    for role in ping_roles:
        roles_str += f"<@&{role.roleId}> "

    race_kwargs = ladder_kwargs.copy()

    if race.mode_obj.archetype_obj.ladder:
        race_kwargs['goal'] = f"Beat The Game (1v1)"
        race_kwargs['partitionable'] = True
        # race_kwargs['hide_entrants'] = True

    room_name = await ac.racetime_service.start_race(
        # We use info_user because it will be concatenated with info_bot later
        info_user=f"Step Ladder Series - [{race.mode_obj.archetype_obj.name}] - {race.mode_obj.name}",
        **race_kwargs,
    )

    races_channel_id = ac.database_service.get_setting("races_channel_id")
    if races_channel_id:
        message = f"{roles_str}\n**[{race.mode_obj.archetype_obj.name}] {race.mode_obj.name}** -- {ac.racetime_service.get_raceroom_url(room_name)} -- <t:{int(delta_ts)}:R>"
        if race.mode_obj.archetype_obj.ladder:
            message += f"\n**This is a 1v1 ladder race using the partitioning system in rt.gg**"
        await ac.discord_service.send_message(
            content=message,
            channel_id=races_channel_id
        )

    ac.database_service.add_fired_race(room_name, race)
    await update_schedule_message()
    return room_name


async def roll_seed(race_id: int):
    """
    Rolls a seed for the given slug and namespace.
    """
    race = ac.database_service.get_scheduled_race_by_id(race_id)

    if not race.raceId:
        logger.error(f"Cannot roll seed! Race {race.id} does not have a race room.")
        return

    room_name = ac.database_service.get_race_by_id(race.raceId).raceRoom.lstrip("/")

    namespace = race.mode_obj.slug.split("/")[0] if "/" in race.mode_obj.slug else None
    slug = (
        race.mode_obj.slug.split("/")[1]
        if "/" in race.mode_obj.slug
        else race.mode_obj.slug
    )
    seed_info = await ac.avianart_service.generate_seed(slug, True, namespace=namespace)

    retry_count = 0
    while retry_count < 10:
        if room_name not in ac.racetime_service.handlers:
            logger.error(f"Room {room_name} not found in handlers, retrying...")
            await asyncio.sleep(5)
            retry_count += 1
            continue
        break
    race_handler: LadderRaceHandler = ac.racetime_service.handler_objects.get(
        room_name, None
    )

    if race_handler:
        await race_handler.send_message(
            f"Here is your seed: https://alttpr.racing/getseed.php?race={race.raceId}"
        )
        hash_str = seed_response_to_hash(seed_info.response)
        await race_handler.set_bot_raceinfo(
            f"{race.mode_obj.slug} - https://alttpr.racing/getseed.php?race={race.raceId} - ({hash_str})"
        )
    else:
        logger.error(f"No handler found for room: {room_name}")

    await ac.discord_service.send_message(
        content=f"Seed for race {race.raceId}: https://avianart.games/perm/{seed_info.response.hash} (https://alttpr.racing/getseed.php?race={race.raceId})",
    )

    # TODO: Supress embeds

    racers = race_handler.data.get("entrants", [])
    savior_message = None
    if (not race.mode_obj.archetype_obj.ladder and len(racers) == 1) or (race.mode_obj.archetype_obj.ladder and len(racers) % 2 == 1):
        savior_roles = ac.database_service.get_savior_roles(
            race.mode_obj.archetype_obj.id
        )
        logger.debug(f"Only one racer found, pinging savior role(s).")
        if savior_roles:
            roles_str = " ".join([f"<@&{role.roleId}>" for role in savior_roles])
        savior_message = f"{roles_str} - There is only one racer for the following race!\n**{race.mode_obj.name}** -- {ac.racetime_service.get_raceroom_url(room_name)}"
        if race.mode_obj.archetype_obj.ladder and len(racers) % 2 == 1:
            savior_message = f"{roles_str} - This is a ladder race and there are an odd number of entrants!\n**{race.mode_obj.name}** -- {ac.racetime_service.get_raceroom_url(room_name)}"

    if savior_message:
        await ac.discord_service.send_message(
                content=savior_message,
            )

async def ping_unready(race_id: int):
    """
    Pings @unready in the Discord channel and racetime.
    """

    race = ac.database_service.get_scheduled_race_by_id(race_id)

    if not race.raceId:
        logger.error(f"Cannot ping unready! Race {race.id} does not have a race room.")
        return

    room_name = ac.database_service.get_race_by_id(race.raceId).raceRoom.lstrip("/")
    retry_count = 0
    while retry_count < 10:
        if room_name not in ac.racetime_service.handlers:
            logger.error(f"Room {room_name} not found in handlers, retrying...")
            await asyncio.sleep(5)
            retry_count += 1
            continue
        break

    race_handler: LadderRaceHandler = ac.racetime_service.handler_objects.get(
        room_name, None
    )

    await race_handler.send_message(
        "@unready Race starting in less than a minute! Ready up or you will be removed!"
    )


async def warn_partitioned_race(race_id: int):
    """
    Warn users that the race is about to be partitioned.
    """

    race = ac.database_service.get_scheduled_race_by_id(race_id)

    if not race.raceId:
        logger.error(f"Cannot warn partitioned race! Race {race.id} does not have a race room.")
        return

    room_name = ac.database_service.get_race_by_id(race.raceId).raceRoom.lstrip("/")
    retry_count = 0
    while retry_count < 10:
        if room_name not in ac.racetime_service.handlers:
            logger.error(f"Room {room_name} not found in handlers, retrying...")
            await asyncio.sleep(5)
            retry_count += 1
            continue
        break

    race_handler: LadderRaceHandler = ac.racetime_service.handler_objects.get(
        room_name, None
    )

    await race_handler.send_message(
        "@entrants Race is about to be partitioned! You will have ~2 minutes to ready up in the partitioned room or you will be disqualified!"
    )
    await race_handler.send_message(
        "If there are an odd number of entrants at the time of partitioning, the last entrant to join will be removed automatically."
    )


async def force_start_race(race_id: int = None, race_room: str = None, ladder: bool = False):
    """
    Forces the start of the race in the Discord channel and racetime.
    """

    if not race_room and not ladder:
        race = ac.database_service.get_scheduled_race_by_id(race_id)

        if not race.raceId:
            logger.error(
                f"Cannot force start race! Race {race.id} does not have a race room."
            )
            return
        room_name = ac.database_service.get_race_by_id(race.raceId).raceRoom.lstrip("/")
    elif race_room and ladder:
        room_name = race_room.lstrip("/")
        race = ac.database_service.get_partitioned_race_by_room_name(room_name).parentRace.scheduledRace

    retry_count = 0
    while retry_count < 10:
        if room_name not in ac.racetime_service.handlers:
            logger.error(f"Room {room_name} not found in handlers, retrying...")
            await asyncio.sleep(5)
            retry_count += 1
            continue
        break

    race_handler: LadderRaceHandler = ac.racetime_service.handler_objects.get(
        room_name, None
    )

    ready = 0
    for entrant in race_handler.data.get("entrants", []):
        if entrant["status"] == "ready":
            ready += 1

    if (ready < 2 and not race.mode_obj.archetype_obj.ladder) or ((len(race_handler.data.get("entrants", [])) < 2) and race.mode_obj.archetype_obj.ladder):
        logger.error(
            f"Not enough ready players to force start race {race.id}. Cancelling."
        )
        await ac.discord_service.send_message(
            content=f"Not enough ready players to force start race {race.id}. Cancelling."
        )
        await race_handler.send_message(
            "Not enough ready players to start the race! Race cancelled."
        )
        await race_handler.cancel_race()
        return

    await ac.discord_service.send_message(
        content=f"Force starting race in racetime room {room_name}."
    )
    await race_handler.send_message("Force starting race! Get ready!")
    try:
        await race_handler.force_start()
    except Exception as e:
        logger.error(f"Failed to force start race {race.id}: {e}")
        await ac.discord_service.send_message(
            content=f"Failed to force start race {race.id}: {e}"
        )
    post_race_channel_id = ac.database_service.get_setting("post_race_channel_id")

    if post_race_channel_id:
        await ac.discord_service.send_message(
            channel_id=post_race_channel_id,
            content=f"==================== ** [{race.mode_obj.archetype_obj.name}] {race.mode_obj.name}** ===================="
        )
        await ac.discord_service.send_message(
            channel_id=post_race_channel_id,
            content=f"_Please remember to use spoiler tags (`||`{random.choice(random_post_race_messages)}`||`) when discussing before the race is completed!_"
        )



def get_schedule_message(num_races: int = 10) -> str:
    """
    Generates a message with the current schedule
    """
    content = "**Step Ladder Schedule** (Times are local)\n"
    upcoming_races = ac.database_service.get_future_scheduled_races(limit=num_races)
    previous_race = ac.database_service.get_previous_race()
    schedule = [previous_race] + upcoming_races

    for n, entry in enumerate(schedule):
        content += f"<t:{int(entry.time.replace(tzinfo=est).timestamp())}:f> (<t:{int(entry.time.replace(tzinfo=est).timestamp())}:R>) - **{entry.mode_obj.name}**"
        if entry.raceId != -1 and entry.raceId is not None:
            race = ac.database_service.get_race_by_id(entry.raceId)
            content += f" - {ac.racetime_service.get_raceroom_url(race.raceRoom)}"
        if n < len(schedule) - 1:
            content += "\n"

    return content


async def update_schedule_message() -> None:
    """
    Updates the schedule message in the specified channel.
    """
    schedule_message_id = ac.database_service.get_setting("schedule_message_id")
    schedule_channel_id = ac.database_service.get_setting("schedule_channel_id")
    schedule_num_races = ac.database_service.get_setting("schedule_num_races")
    if not schedule_message_id or not schedule_channel_id or not schedule_num_races:
        return
    content = get_schedule_message(schedule_num_races)
    await ac.discord_service.bot.rest.edit_message(
        channel=schedule_channel_id,
        message=schedule_message_id,
        content=content,
    )


async def schedule_future_races() -> None:
    future_races = ac.database_service.get_future_scheduled_races()
    scheduled_jobs = set([x.id for x in ac.scheduler_service.scheduler.get_jobs()])

    race_jobs = [
        "open_race_",
        "roll_seed_",
        "ping_unready_",
        "force_start_",
    ]

    # For each job, check that all scheduled components exist, if one missing, schedule the whole race
    logger.info("Scheduling future races...")
    for race in future_races:
        for job in race_jobs:
            if f"{job}{race.id}" not in scheduled_jobs:
                ac.scheduler_service.schedule_race(race.id)
    logger.info("All future races have been scheduled.")
    await update_schedule_message()


def estnow() -> datetime.datetime:
    """
    Returns the current time in EST.
    """
    return datetime.datetime.now(est)


def seed_response_to_hash(response: AvianResponsePayload) -> str:
    if response.fshash:
        return convert_hash(response.fshash)
    elif response.spoiler["meta"]["hash"]:
        return convert_hash(response.spoiler["meta"]["hash"])
    else:
        return "No hash available"


def convert_hash(hash_str: str) -> str:
    """
    Converts a hash string to a format suitable for use in URLs.
    """
    hash_conversions = {
        "Bomb": "Bombs",
        "Powder": "Magic Powder",
        "Rod": "Ice Rod",
        "Ocarina": "Flute",
        "Bug Net": "Bugnet",
        "Bottle": "Empty Bottle",
        "Potion": "Green Potion",
        "Cane": "Somaria",
        "Pearl": "Moon Pearl",
        "Key": "Big Key",
    }
    hash_list = hash_str.split(", ")
    hash_str = "/".join([hash_conversions.get(item, item) for item in hash_list])
    return hash_str
