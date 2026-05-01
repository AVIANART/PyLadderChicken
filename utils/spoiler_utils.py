import json
import logging
import os
import tempfile

import app_context as ac
from config import import_config

from pathlib import Path

from services.avianart import AvianResponsePayload
import spoiler_converter


logger = logging.getLogger("pyladderchicken")
config = import_config()

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
    seed: AvianResponsePayload, race_id: int, upload: bool = True
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
            ac.database_service.add_spoiler_to_race(race_id, f"{config['s3_public_bucket_url']}/{transformed_output.name}")
            os.remove(transformed_output)
            return transformed_output.name
        else:
            logger.error(f"Failed to upload spoiler file {transformed_output} to S3.")
            return None

    logger.info(f"Transformed spoiler file saved to {transformed_output}")
    return transformed_output
