import asyncio
import json
import os
from pathlib import Path
import random
import tempfile
from typing import TYPE_CHECKING
import zoneinfo
import datetime
from apscheduler.triggers.date import DateTrigger


import datetime
import logging

import hikari

from services.avianart import AvianResponsePayload
import app_context as ac
import spoiler_converter
from config import import_config

if TYPE_CHECKING:
    from services.racetime import LadderRaceHandler

config = import_config()

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
    "hide_entrants": False,
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
    "I should learn glitches...",
]

possible_prizes = {
    "Small Heart": 0xD8,
    "Fairy": 0xE3,
    "Rupee (1)": 0xD9,
    "Rupees (5)": 0xDA,
    "Rupees (20)": 0xDB,
    "Big Magic": 0xE0,
    "Small Magic": 0xDF,
    "Single Bomb": 0xDC,
    "Bombs (4)": 0xDD,
    "Bombs (8)": 0xDE,
    "Arrows (5)": 0xE1,
    "Arrows (10)": 0xE2,
}

possible_mem_locs_to_prizes = {v: k for k, v in possible_prizes.items()}

ENEMY_GROUP_NAMES = {
    1: "HeartsGroup",
    2: "RupeesGroup",
    3: "MagicGroup",
    4: "BombsGroup",
    5: "ArrowsGroup",
    6: "SmallVarietyGroup",
    7: "LargeVarietyGroup",
}


def get_prize_pack_name(prize_pack_set):
    if prize_pack_set[0] == "Small Heart":  # Heart
        if prize_pack_set[1] == "Fairy":  # Fairy
            return "LargeVarietyPack"
        return "HeartsPack"
    if prize_pack_set[0] == "Rupees (5)":  # RupeeBlue
        return "RupeesPack"
    if prize_pack_set[0] == "Single Bomb":  # BombRefill1
        return "BombsPack"
    if prize_pack_set[0] == "Small Magic":  # MagicRefillSmall
        return "SmallVarietyPack"
    if prize_pack_set[0] == "Big Magic":  # MagicRefillFull
        return "MagicPack"
    if prize_pack_set[0] == "Arrows (5)":  # ArrowRefill5
        return "ArrowsPack"


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
        race_kwargs["goal"] = f"Beat The Game (1v1)"
        race_kwargs["partitionable"] = True
        # race_kwargs['hide_entrants'] = True

    # if race.mode_obj.archetype_obj.spoiler:
    #     race_kwargs["start_delay"] = 15 + (15 * 60)  # 15 min delay for spoiler for prep time

    room_name = await ac.racetime_service.start_race(
        # We use info_user because it will be concatenated with info_bot later
        info_user=f"Step Ladder Series - [{race.mode_obj.archetype_obj.name}] - {race.mode_obj.name}",
        **race_kwargs,
    )

    races_channel_id = ac.database_service.get_setting("races_channel_id")
    message = f"{roles_str}\n**[{race.mode_obj.archetype_obj.name}] {race.mode_obj.name}** -- {ac.racetime_service.get_raceroom_url(room_name)} -- <t:{int(delta_ts)}:R>"
    if race.mode_obj.archetype_obj.ladder:
        message += (
            f"\n**This is a 1v1 ladder race using the partitioning system in rt.gg**"
        )
    if races_channel_id:
        await ac.discord_service.send_message(
            content=message, channel_id=races_channel_id
        )
    await ac.discord_service.send_message(content=message)

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
    seed_info = await ac.avianart_service.generate_seed(
        slug,
        True,
        namespace=namespace,
        spoiler=True if race.mode_obj.archetype_obj.spoiler else False,
    )

    if race.mode_obj.archetype_obj.spoiler:
        spoiler_name = avianart_payload_to_spoiler(seed_info, upload=True)
        if spoiler_name:
            await ac.discord_service.send_message(
                content=f"Spoiler for seed {seed_info.response.hash} uploaded successfully: {config['s3_public_bucket_url']}/{spoiler_name}",
                suppress_embeds=True,
            )
            race_utc_datetime = race.time.replace(tzinfo=est).astimezone(utc)
            # Schedule spoiler to be posted at the same time as the seed starts
            ac.scheduler_service.scheduler.add_job(
                post_spoiler,
                trigger=DateTrigger(run_date=race_utc_datetime),
                args=[spoiler_name, race_id],
                id=f"post_spoiler_{race_id}",
            )

            for minutes in [10, 5, 3, 2, 1, 0]:
                ac.scheduler_service.scheduler.add_job(
                    post_prep_time_left,
                    trigger=DateTrigger(
                        run_date=race_utc_datetime
                        + datetime.timedelta(minutes=15)
                        - datetime.timedelta(minutes=minutes)
                    ),
                    kwargs={"race_id": race_id, "remaining_time_minutes": minutes},
                    id=f"prep_time_left_{race_id}_{minutes}m",
                )

            for seconds in [30, 15, 10, 5, 4, 3, 2, 1]:
                ac.scheduler_service.scheduler.add_job(
                    post_prep_time_left,
                    trigger=DateTrigger(
                        run_date=race_utc_datetime
                        + datetime.timedelta(minutes=15)
                        - datetime.timedelta(seconds=seconds)
                    ),
                    kwargs={"race_id": race_id, "remaining_time_seconds": seconds},
                    id=f"prep_time_left_{race_id}_{seconds}s",
                )

        else:
            admin_role = ac.database_service.get_setting("admin_role_id")
            admin_ping = f"<@&{admin_role}> " if admin_role else ""
            await ac.discord_service.send_message(
                content=f"{admin_ping}Failed to upload spoiler file for race {race_id} with seed ID {seed_info.response.hash}!",
                force_mention=True,
            )

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
        hash_str = seed_response_to_hash(seed_info.response)
        await race_handler.send_message(
            f"Here is your seed: https://alttpr.racing/getseed.php?race={race.raceId} - ({hash_str})"
        )
        await race_handler.set_bot_raceinfo(
            f"{race.mode_obj.slug} - https://alttpr.racing/getseed.php?race={race.raceId} - ({hash_str})"
        )
    else:
        logger.error(f"No handler found for room: {room_name}")

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
            content=f"{admin_ping}Failed to update race {race_id} with seed ID {seed_info.response.hash}.",
            force_mention=True,
        )

    await ac.discord_service.send_message(
        content=f"Seed for race {race_id}: https://avianart.games/perm/{seed_info.response.hash} (https://alttpr.racing/getseed.php?race={race_id})",
        suppress_embeds=True,
    )

    # TODO: Supress embeds

    racers = race_handler.data.get("entrants", [])
    savior_message = None
    if (not race.mode_obj.archetype_obj.ladder and len(racers) == 1) or (
        race.mode_obj.archetype_obj.ladder and len(racers) % 2 == 1
    ):
        savior_roles = ac.database_service.get_savior_roles(
            race.mode_obj.archetype_obj.id
        )
        logger.debug(f"Only one racer found, pinging savior role(s).")
        if savior_roles:
            roles_str = " ".join([f"<@&{role.roleId}>" for role in savior_roles])
        savior_message = f"{roles_str} - There is only one racer for the following race!\n**{race.mode_obj.name}** -- {ac.racetime_service.get_raceroom_url(room_name)}"
        if race.mode_obj.archetype_obj.ladder and len(racers) % 2 == 1:
            savior_message = f"{roles_str} - This is a ladder race and there are an odd number of entrants!\n**{race.mode_obj.name}** -- {ac.racetime_service.get_raceroom_url(room_name)}"
    races_channel_id = ac.database_service.get_setting("races_channel_id")

    if races_channel_id and savior_message:
        await ac.discord_service.send_message(
            content=savior_message, channel_id=races_channel_id
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
        logger.error(
            f"Cannot warn partitioned race! Race {race.id} does not have a race room."
        )
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


async def force_start_race(
    race_id: int = None,
    race_room: str = None,
    ladder: bool = False,
    suppress_post_race_message: bool = False,
):
    """
    Forces the start of the race in the Discord channel and racetime.
    """

    if not race_room and not ladder:
        race = ac.database_service.get_scheduled_race_by_id(race_id)

        if not race.raceId:
            logger.error(
                f"Cannot force start race! Race {race.raceId} does not have a race room."
            )
            return
        room_name = ac.database_service.get_race_by_id(race.raceId).raceRoom.lstrip("/")
    elif race_room and ladder:
        room_name = race_room.lstrip("/")
        race = ac.database_service.get_partitioned_race_by_room_name(
            room_name
        ).parentRace.scheduledRace

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
        if entrant["status"]["value"] == "ready":
            ready += 1

    if (ready < 2 and not race.mode_obj.archetype_obj.ladder) or (
        (len(race_handler.data.get("entrants", [])) < 2)
        and race.mode_obj.archetype_obj.ladder
    ):
        logger.error(
            f"Not enough ready players to force start race {race.raceId}. Cancelling."
        )
        await ac.discord_service.send_message(
            content=f"Not enough ready players to force start race {race.raceId}. Cancelling."
        )
        await race_handler.send_message(
            "Not enough ready players to start the race! Race cancelled."
        )

        # Cleanup scheduled jobs for spoiler
        if race.mode_obj.archetype_obj.spoiler:
            all_jobs = ac.scheduler_service.scheduler.get_jobs()
            race_jobs = [
                x
                for x in all_jobs
                if x.id.startswith(f"prep_time_left_{race_id}_")
                or x.id.startswith(f"post_spoiler_{race_id}")
            ]

            for job in race_jobs:
                ac.scheduler_service.scheduler.remove_job(job.id)

        await race_handler.cancel_race()
        return

    await race_handler.send_message("Force starting race! Get ready!")
    try:
        await race_handler.force_start()
    except Exception as e:
        logger.error(f"Failed to force start race {race.raceId}: {e}")

        admin_role = ac.database_service.get_setting("admin_role_id")
        admin_ping = f"<@&{admin_role}> " if admin_role else ""

        await ac.discord_service.send_message(
            content=f"{admin_ping}Failed to force start race {race.raceId}: {e}",
            force_mention=True,
        )
    post_race_channel_id = ac.database_service.get_setting("post_race_channel_id")

    if post_race_channel_id and not suppress_post_race_message:
        thread: hikari.GuildThreadChannel = (
            await ac.discord_service.bot.rest.create_thread(
                post_race_channel_id,
                hikari.ChannelType.GUILD_PUBLIC_THREAD,
                f"[{race.mode_obj.archetype_obj.name}] {race.mode_obj.name} - {room_name.split('/')[-1]} ",
            )
        )

        await thread.send(f"_{random.choice(random_post_race_messages)}_")


async def post_prep_time_left(
    race_id: int,
    remaining_time_minutes: int = None,
    remaining_time_seconds: int = None,
):
    race = ac.database_service.get_scheduled_race_by_id(race_id)
    room_name = ac.database_service.get_race_by_id(race.raceId).raceRoom.lstrip("/")

    race_handler: LadderRaceHandler = ac.racetime_service.handler_objects.get(
        room_name, None
    )

    if not race_handler:
        logger.error(f"post_prep_time_left: No handler found for room: {room_name}")
        return

    if remaining_time_minutes == 0:
        await race_handler.send_message(
            "Prep time is over! You can now start the seed, GLHF!"
        )

    elif remaining_time_minutes:
        await race_handler.send_message(
            f"{remaining_time_minutes} minutes of prep time remain!"
        )
    elif remaining_time_seconds:
        await race_handler.send_message(f"{remaining_time_seconds} seconds remain!")


async def post_spoiler(
    spoiler_name: str, race_id: int = None, prep_time_minutes: int = 15
):
    """
    Posts the spoiler for the race to the racetime chat. Must pin this message in the channel for it to be visible.
    """
    race = ac.database_service.get_scheduled_race_by_id(race_id)
    room_name = ac.database_service.get_race_by_id(race.raceId).raceRoom.lstrip("/")

    race_handler: LadderRaceHandler = ac.racetime_service.handler_objects.get(
        room_name, None
    )

    if not race_handler:
        logger.error(f"No handler found for room: {room_name}")

        admin_role = ac.database_service.get_setting("admin_role_id")
        admin_ping = f"<@&{admin_role}> " if admin_role else ""

        await ac.discord_service.send_message(
            content=f"{admin_ping}Failed to post spoiler for race, could not find race handler for room {room_name}!",
            force_mention=True,
        )
        return

    # Pinned messages get sent to the top of the chat, so we send the spoiler as a pinned message first,
    # then again as a normal message so it doesn't get buried in the chat but is still visible.
    await race_handler.send_message(
        f"Spoiler for this seed: {config['s3_public_bucket_url']}/{spoiler_name}",
        pinned=True,
    )

    await race_handler.send_message(
        f"Spoiler for this seed: {config['s3_public_bucket_url']}/{spoiler_name}",
    )
    if prep_time_minutes > 0:
        await race_handler.send_message(
            f"{prep_time_minutes} minutes of prep time starts now! A message will be posted when you can start the seed!",
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
        if entry.mode_obj.archetype_obj.ladder:
            content += " (1v1)"
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

    _race_jobs = [
        "open_race_",
        "roll_seed_",
        "force_start_",
    ]

    # For each job, check that all scheduled components exist, if one missing, schedule the whole race
    logger.info("Scheduling future races...")
    for race in future_races:
        if race.mode_obj.archetype_obj.ladder:
            race_jobs = _race_jobs.copy() + ["warn_partitioned_"]
        else:
            race_jobs = _race_jobs.copy() + ["ping_unready_"]
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
    hash_str = "/".join(
        [
            f'Hash{hash_conversions.get(item, item).replace(" ", "")}'
            for item in hash_list
        ]
    )
    return hash_str


def find_jsonrom_byte(patch_data, address):
    target = int(address, 16) if isinstance(address, str) else int(address)
    for start_str, values in patch_data.items():
        start = int(start_str)
        if start <= target < start + len(values):
            return values[target - start]
    return None


def add_extra_info_to_spoiler(seed: AvianResponsePayload) -> dict:
    """Not everything is available in the spoiler yet, so we need to add some extra info by parsing the patch data."""
    spoiler = seed.response.spoiler.copy()
    spoiler["Special"]["DiggingGameDigs"] = find_jsonrom_byte(
        seed.response.patch, 0x180020
    )
    spoiler["Drops"] = {}
    spoiler["Drops"]["PullTree"] = {}
    spoiler["Drops"]["PullTree"]["Tier1"] = possible_mem_locs_to_prizes[
        find_jsonrom_byte(seed.response.patch, (0xEFBD4))
    ]
    spoiler["Drops"]["PullTree"]["Tier2"] = possible_mem_locs_to_prizes[
        find_jsonrom_byte(seed.response.patch, (0xEFBD5))
    ]
    spoiler["Drops"]["PullTree"]["Tier3"] = possible_mem_locs_to_prizes[
        find_jsonrom_byte(seed.response.patch, (0xEFBD6))
    ]

    spoiler["Drops"]["RupeeCrab"] = {}
    spoiler["Drops"]["RupeeCrab"]["Main"] = possible_mem_locs_to_prizes[
        find_jsonrom_byte(seed.response.patch, 0x329C8)
    ]
    spoiler["Drops"]["RupeeCrab"]["Final"] = possible_mem_locs_to_prizes[
        find_jsonrom_byte(seed.response.patch, 0x329C4)
    ]

    spoiler["Drops"]["Stun"] = possible_mem_locs_to_prizes[
        find_jsonrom_byte(seed.response.patch, 0x37993)
    ]
    spoiler["Drops"]["FishSave"] = possible_mem_locs_to_prizes[
        find_jsonrom_byte(seed.response.patch, 0xE82CC)
    ]

    spoiler["PrizePacks"] = {}

    prize_vals = []
    prizes_loc = 0x37A78
    for i in range(7):
        pack = []
        for j in range(8):
            prize = possible_mem_locs_to_prizes[
                find_jsonrom_byte(seed.response.patch, prizes_loc + (i * 8 + j))
            ]
            pack.append(prize)
        prize_vals.append(pack)

    for group_index, prize_pack_set in enumerate(prize_vals, 1):
        group_name = ENEMY_GROUP_NAMES.get(group_index, f"Group{group_index}")
        prize_pack_name = get_prize_pack_name(prize_pack_set)
        spoiler["PrizePacks"][group_name] = prize_pack_name
        # drop_order = ', '.join(prize_pack_set)
        # spoiler["PrizePacks"][group_name] = {
        #     f'PrizePackName': prize_pack_name,
        #     f'DropOrder': drop_order,
        # }

    return spoiler


def avianart_payload_to_spoiler(
    seed: AvianResponsePayload, upload: bool = True
) -> Path | None:
    json_spoiler_tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", encoding="utf-8", delete=False
    )
    spoiler = add_extra_info_to_spoiler(seed)

    try:
        json.dump(spoiler, json_spoiler_tmp)
        json_spoiler_tmp.flush()
        json_spoiler_tmp.close()

        transformed_output = (
            Path(tempfile.gettempdir())
            / f"Spoiler_StepLadder_{seed.response.hash}_{'-'.join(spoiler['meta']['hash'].split(',')).replace(' ', '')}.json"
        )
        spoiler_converter.transform(json_spoiler_tmp.name, transformed_output)
    finally:
        try:
            Path(json_spoiler_tmp.name).unlink(missing_ok=True)
        except OSError:
            pass
    if upload:
        uploaded = ac.s3_service.upload_file(
            str(transformed_output), transformed_output.name
        )

        if uploaded:
            logger.info(
                f"Spoiler file {transformed_output} uploaded successfully to S3."
            )
            os.remove(transformed_output)
            return transformed_output.name
        else:
            logger.error(f"Failed to upload spoiler file {transformed_output} to S3.")
            return None

    logger.info(f"Transformed spoiler file saved to {transformed_output}")
    return transformed_output
