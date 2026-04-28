"""
Parse jsonout from DR/OWR into a better, community standard format.

Original implementation by clearmouse
Design by Jem and telethar
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

from data.spoiler_data import (
    ITEM_NAMES_CONVERTER,
    DROP_NAMES_CONVERTER,
    PRIZE_NAMES_CONVERTER,
    LOCATION_NAME_EXCEPTION_CONVERTER,
    LOCATION_NAME_REPLACEMENTS,
    ENTRANCE_NAME_REPLACEMENTS,
    ENTRANCE_AT_NAME_REPLACEMENTS,
    ENTRANCE_LOCATIONS_EXCLUDE_LIST,
    DUNGEON_PRIZE_KEY_MAP,
    FOLLOWER_DESTINATION_MAP,
    FOLLOWER_BRANCH_MAP,
    BOSS_NAMES,
    ENEMY_NAMES,
)


DUNGEON_OUTPUT_SECTIONS = [
    "Hyrule Castle",
    "Eastern Palace",
    "Desert Palace",
    "Tower Of Hera",
    "Castle Tower",
    "Dark Palace",
    "Swamp Palace",
    "Skull Woods",
    "Thieves Town",
    "Ice Palace",
    "Misery Mire",
    "Turtle Rock",
    "Ganons Tower",
]

WORLD_OUTPUT_SECTIONS = ["Light World", "Death Mountain", "Dark World"]
ALL_LOCATION_OUTPUT_SECTIONS = WORLD_OUTPUT_SECTIONS + DUNGEON_OUTPUT_SECTIONS

INPUT_DUNGEON_TO_OUTPUT = {
    "Hyrule Castle": "Hyrule Castle",
    "Eastern Palace": "Eastern Palace",
    "Desert Palace": "Desert Palace",
    "Tower of Hera": "Tower Of Hera",
    "Agahnims Tower": "Castle Tower",
    "Palace of Darkness": "Dark Palace",
    "Swamp Palace": "Swamp Palace",
    "Skull Woods": "Skull Woods",
    "Thieves Town": "Thieves Town",
    "Ice Palace": "Ice Palace",
    "Misery Mire": "Misery Mire",
    "Turtle Rock": "Turtle Rock",
    "Ganons Tower": "Ganons Tower",
}


_TEMPLATES_PATH = Path(__file__).parent / "data" / "spoiler_orders.json"

ENEMY_SUFFIX_RE = re.compile(r"\s*\([A-Za-z0-9]+\)$")


def _load_templates() -> dict:
    with open(_TEMPLATES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _strip_enemy_suffix(key: str) -> str:
    m = ENEMY_SUFFIX_RE.search(key)
    if not m:
        return key
    inside = m.group(0).strip()[1:-1]
    if inside in ENEMY_NAMES or inside in {b.replace(" ", "") for b in BOSS_NAMES}:
        return key[: m.start()]
    return key


def _apply_location_renames(key: str) -> str:
    """Apply renames iteratively (longest-first each pass)
    so cascading renames work, e.g. "Blinds Hideout (Top) Pot #2" ->
    "Blind's Hideout (Top) Pot #2" -> "Blind's Hideout - Top Pot #2".
    """
    # Whole-key exception map first.
    if key in LOCATION_NAME_EXCEPTION_CONVERTER:
        key = LOCATION_NAME_EXCEPTION_CONVERTER[key]

    sorted_prefixes = sorted(
        LOCATION_NAME_REPLACEMENTS.items(), key=lambda kv: -len(kv[0])
    )
    applied: set[str] = set()
    # Gate at 8 iterations to prevent infinite loops in case of a bug in the rename maps.
    for _ in range(8):
        changed = False
        for old_prefix, new_prefix in sorted_prefixes:
            if old_prefix == new_prefix or old_prefix in applied:
                continue
            if old_prefix in key:
                new_key = key.replace(old_prefix, new_prefix)
                if new_key != key:
                    key = new_key
                    applied.add(old_prefix)
                    changed = True
                    break
        if not changed:
            break
    return key


def _convert_item(value: str) -> str:
    """Convert a raw spoiler item string to the new output value."""
    stripped = re.sub(r"\s*\(Player \d+\)$", "", value)
    if stripped in ITEM_NAMES_CONVERTER:
        return ITEM_NAMES_CONVERTER[stripped]
    if stripped in DROP_NAMES_CONVERTER:
        return DROP_NAMES_CONVERTER[stripped]
    if stripped in PRIZE_NAMES_CONVERTER:
        return PRIZE_NAMES_CONVERTER[stripped]
    return stripped


def _build_template_index(
    templates: dict,
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Return (key_base -> section, section -> ordered keys)."""
    locations = templates["locations"]
    key_to_section: dict[str, str] = {}
    section_order: dict[str, list[str]] = {}
    for section in ALL_LOCATION_OUTPUT_SECTIONS:
        ordered = locations.get(section, [])
        section_order[section] = ordered
        for k in ordered:
            key_to_section[k] = section
    return key_to_section, section_order


def _build_entrance_template_index(
    templates: dict,
) -> tuple[dict[str, str], dict[str, list[str]]]:
    entrances = templates["entrances"]
    key_to_category: dict[str, str] = {}
    category_order: dict[str, list[str]] = {}
    for category, keys in entrances.items():
        category_order[category] = keys
        for k in keys:
            key_to_category[k] = category
    return key_to_category, category_order


def _lookup_prize_in_input(section: dict, input_dungeon: str) -> Any:
    """Find a "<Dungeon> - Prize" value tolerating apostrophe/space variants."""
    if input_dungeon == "Thieves Town":
        lookup = "Thieves' Town - Prize"
    else:
        lookup = f"{input_dungeon} - Prize"

    if lookup in section:
        return section[lookup], lookup
    return None, None


def _emit_prizes(
    data: dict,
    bosses: dict[str, str],
    boss_shuffle_active: bool,
) -> "dict[str, str]":
    """Collect <Dungeon> - Prize entries from input dungeon sections."""
    out: "dict[str, str]" = {}
    for input_dungeon, output_dungeon in INPUT_DUNGEON_TO_OUTPUT.items():
        if output_dungeon not in DUNGEON_PRIZE_KEY_MAP:
            continue
        section = data.get(input_dungeon, {})
        prize_value, _ = _lookup_prize_in_input(section, input_dungeon)
        if prize_value is None:
            continue
        prize_converted = PRIZE_NAMES_CONVERTER.get(prize_value, prize_value)
        prize_key = DUNGEON_PRIZE_KEY_MAP[output_dungeon]
        if boss_shuffle_active:
            boss_name = bosses.get(input_dungeon)
            if boss_name and "Ganon" not in prize_key:
                prize_key = f"{prize_key} ({boss_name})"
        out[prize_key] = prize_converted

    if boss_shuffle_active:
        for gt_room in (
            "Ganons Tower Basement",
            "Ganons Tower Middle",
            "Ganons Tower Top",
        ):
            boss_name = bosses.get(gt_room)
            if boss_name:
                out[f"{gt_room} ({boss_name})"] = "None"
    return out


def _emit_special(data: dict) -> "dict[str, Any]":
    out: "dict[str, Any]" = {}
    special = data.get("Special", {})
    bottles = data.get("Bottles", {})
    if "Misery Mire" in special:
        out["Misery Mire Medallion"] = special["Misery Mire"]
    if "Turtle Rock" in special:
        out["Turtle Rock Medallion"] = special["Turtle Rock"]
    if "Waterfall Bottle" in bottles:
        out["Waterfall Bottle"] = ITEM_NAMES_CONVERTER.get(
            bottles["Waterfall Bottle"], bottles["Waterfall Bottle"]
        )
    if "Pyramid Bottle" in bottles:
        out["Pyramid Bottle"] = ITEM_NAMES_CONVERTER.get(
            bottles["Pyramid Bottle"], bottles["Pyramid Bottle"]
        )
    digs = special.get("DiggingGameDigs", None)

    if digs is not None:
        out["DiggingGameDigs"] = digs
    return out


def _gather_input_locations(data: dict) -> Iterable[tuple[str, str]]:
    """Yield (input_location_key, raw_value) for every placement entry in input.

    We pull from Light World, Dark World, Caves, and each dungeon section.
    """
    for source in ("Light World", "Dark World", "Caves") + tuple(
        INPUT_DUNGEON_TO_OUTPUT.keys()
    ):
        section = data.get(source)
        if not isinstance(section, dict):
            continue
        for key, value in section.items():
            yield key, value


def _classify_location(
    rename_key: str,
    key_to_section: dict[str, str],
) -> tuple[str | None, str]:
    """Resolve which output section a renamed key belongs to."""
    base = _strip_enemy_suffix(rename_key)
    section = key_to_section.get(base)
    return section, base


def _emit_locations(
    data: dict,
    bosses: dict[str, str],
    key_to_section: dict[str, str],
    section_order: dict[str, list[str]],
    followers_dest_set: set[str],
    boss_shuffle_active: bool,
) -> tuple[dict[str, "dict[str, Any]"], "dict[str, str]"]:
    """Build all location sections and the Followers section."""
    buckets: dict[str, dict[str, list[tuple[str, str]]]] = {
        s: {} for s in ALL_LOCATION_OUTPUT_SECTIONS
    }
    followers: "dict[str, str]" = {}

    boss_prize_template_key: dict[str, dict[str, str]] = {}
    for input_dungeon, output_dungeon in INPUT_DUNGEON_TO_OUTPUT.items():
        keys = section_order.get(output_dungeon, [])
        bp = {}
        for k in keys:
            if k.endswith(" - Boss"):
                bp["Boss"] = k
            elif k.endswith(" - Prize"):
                bp["Prize"] = k
        boss_prize_template_key[input_dungeon] = bp

    for raw_key, raw_value in _gather_input_locations(data):
        if raw_key in followers_dest_set:
            dest_name = FOLLOWER_DESTINATION_MAP[raw_key]
            branch_name = FOLLOWER_BRANCH_MAP.get(raw_value, raw_value)
            followers[f"{branch_name} @"] = dest_name
            continue

        # Skip Aga 1/2 placement rows (not present in output).
        if raw_key in ("Agahnim 1", "Agahnim 2"):
            continue

        # Boss / Prize rows -> emit into dungeon section using template key.
        owner = _dungeon_owner(data, raw_key)
        if owner and (raw_key.endswith(" - Boss") or raw_key.endswith(" - Prize")):
            row_kind = "Boss" if raw_key.endswith(" - Boss") else "Prize"
            tmpl_key = boss_prize_template_key.get(owner, {}).get(row_kind)
            if tmpl_key is None:
                continue
            output_dungeon = INPUT_DUNGEON_TO_OUTPUT[owner]
            if row_kind == "Boss":
                converted = _convert_item(raw_value)
            else:
                converted = PRIZE_NAMES_CONVERTER.get(raw_value, raw_value)
            full_key = tmpl_key
            if boss_shuffle_active and row_kind == "Boss":
                boss = bosses.get(owner)
                if boss:
                    full_key = f"{tmpl_key} ({boss})"
            buckets[output_dungeon].setdefault(tmpl_key, []).append(
                (full_key, converted)
            )
            continue

        # Renames
        renamed = _apply_location_renames(raw_key)
        section, base = _classify_location(renamed, key_to_section)

        if section is None:
            section = INPUT_DUNGEON_TO_OUTPUT.get(_dungeon_owner(data, raw_key))
            if section is None:
                continue

        if base not in section_order.get(section, []):
            section_order[section].append(base)

        converted = _convert_item(raw_value)
        buckets[section].setdefault(base, []).append((renamed, converted))

    # Emit
    output_sections: dict[str, "dict[str, Any]"] = {}
    for section in ALL_LOCATION_OUTPUT_SECTIONS:
        ordered: "dict[str, Any]" = {}
        for base_key in section_order[section]:
            entries = buckets[section].get(base_key)
            if not entries:
                continue
            for full_key, value in entries:
                ordered[full_key] = value
        output_sections[section] = ordered
    return output_sections, followers


def _dungeon_owner(data: dict, raw_key: str) -> str | None:
    """Return the input dungeon name that contains raw_key, if any."""
    for dungeon in INPUT_DUNGEON_TO_OUTPUT.keys():
        section = data.get(dungeon, {})
        if isinstance(section, dict) and raw_key in section:
            return dungeon
    return None


def _emit_drops(data: dict) -> "dict[str, Any]" | None:
    drops_in = data.get("Drops")
    if not isinstance(drops_in, dict):
        return None
    out: "dict[str, Any]" = {}
    if "PullTree" in drops_in:
        pt = drops_in["PullTree"]
        out["PullTree"] = dict(
            (tier, DROP_NAMES_CONVERTER.get(v, v)) for tier, v in pt.items()
        )
    if "RupeeCrab" in drops_in:
        rc = drops_in["RupeeCrab"]
        out["RupeeCrab"] = dict(
            (k, DROP_NAMES_CONVERTER.get(v, v)) for k, v in rc.items()
        )
    if "Stun" in drops_in:
        out["Stun"] = DROP_NAMES_CONVERTER.get(drops_in["Stun"], drops_in["Stun"])
    if "FishSave" in drops_in:
        out["FishSave"] = DROP_NAMES_CONVERTER.get(
            drops_in["FishSave"], drops_in["FishSave"]
        )
    return out or None


def _emit_prize_packs(data: dict) -> "dict[str, str]" | None:
    pp = data.get("PrizePacks") or data.get("Prize Packs")
    if not isinstance(pp, dict):
        return None
    return pp


def _emit_entrances(
    data: dict,
    key_to_category: dict[str, str],
    category_order: dict[str, list[str]],
) -> "dict[str, dict[str, str]]":
    """Process Entrances array into the categorised dict shape."""
    raw_entries = data.get("Entrances", []) or []
    pairs: list[tuple[str, str]] = []  # (output_key_with_suffix, entrance_value)

    for entry in raw_entries:
        ent = entry.get("entrance", "")
        ext = entry.get("exit", "")
        direction = entry.get("direction", "entrance")

        if any(name in ent for name in ENTRANCE_LOCATIONS_EXCLUDE_LIST) or any(
            name in ext for name in ENTRANCE_LOCATIONS_EXCLUDE_LIST
        ):
            continue

        ent_renamed = ENTRANCE_NAME_REPLACEMENTS.get(
            ent, ENTRANCE_AT_NAME_REPLACEMENTS.get(ent, ent)
        )
        ext_renamed = ENTRANCE_NAME_REPLACEMENTS.get(
            ext, ENTRANCE_AT_NAME_REPLACEMENTS.get(ext, ext)
        )

        if direction == "exit":
            # one-way reverse: the entrance side is the @-keyed location.
            key, value = f"{ent_renamed} @", ext_renamed
        else:
            # 'entrance' or 'both': exit side is the @-keyed location.
            key, value = f"{ext_renamed} @", ent_renamed

        pairs.append((key, value))

    out: "dict[str, dict[str, str]]" = {}
    seen: set[str] = set()
    for category, ordered_keys in category_order.items():
        cat_dict: "dict[str, str]" = {}
        index = {k: v for k, v in pairs if k in ordered_keys}
        for k in ordered_keys:
            if k in index:
                cat_dict[k] = index[k]
                seen.add(k)
        out[category] = cat_dict

    return out


def _emit_meta(data: dict) -> "dict[str, Any]":
    """Build meta section. Pulls from input.meta and certain top-level fields."""
    meta_in = data.get("meta", {}) or {}
    out: "dict[str, Any]" = {}

    seed = meta_in.get("seed")
    if seed is not None:
        out["seed_number"] = str(seed)

    goal = _first_setting(meta_in, "goal")
    if goal is not None:
        out["goal"] = goal

    gt_crystals = _first_setting(meta_in, "gt_crystals")
    if gt_crystals is not None:
        out["gt_entry_requirement"] = f"{gt_crystals} crystals"

    ganon_crystals = _first_setting(meta_in, "ganon_crystals")
    if ganon_crystals is not None:
        out["ganon_requirement"] = f"{ganon_crystals} crystals"

    custom_goals = meta_in.get("custom_goals", {})
    if isinstance(custom_goals, dict):
        cg = custom_goals.get("1") or {}
        if cg.get("murahgoal") is not None:
            out["murahdahla_requirement"] = cg["murahgoal"]
        if cg.get("pedgoal") is not None:
            out["pedestal_requirement"] = cg["pedgoal"]

    tg = _first_setting(meta_in, "triforcegoal")
    if tg is not None:
        out["triforce_pieces_requirement"] = int(tg)
    tp = _first_setting(meta_in, "triforcepool")
    if tp is not None:
        out["triforce_pieces_total"] = int(tp)

    return out


def _first_setting(meta_in: dict, key: str) -> Any:
    val = meta_in.get(key)
    if isinstance(val, dict):
        for k in ("1", "0"):
            if k in val:
                return val[k]
        return next(iter(val.values()), None)
    return val


def transform(input_path: str | Path, output_path: str | Path) -> None:
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    templates = _load_templates()
    key_to_section, section_order = _build_template_index(templates)
    key_to_category, category_order = _build_entrance_template_index(templates)
    bosses = data.get("Bosses", {}) or {}
    followers_dest_set = set(FOLLOWER_DESTINATION_MAP.keys())

    meta_in = data.get("meta", {}) or {}
    boss_shuffle_setting = _first_setting(meta_in, "boss_shuffle")
    boss_shuffle_active = bool(
        boss_shuffle_setting and str(boss_shuffle_setting).lower() != "none"
    )
    entrance_shuffle = _first_setting(meta_in, "shuffle")
    entrance_shuffle_active = bool(
        entrance_shuffle and str(entrance_shuffle).lower() != "vanilla"
    )

    follower_shuffle_active = bool(_first_setting(meta_in, "shuffle_followers"))

    out: "dict[str, Any]" = {}
    out["Prizes"] = _emit_prizes(data, bosses, boss_shuffle_active)
    out["Special"] = _emit_special(data)

    location_sections, followers = _emit_locations(
        data,
        bosses,
        key_to_section,
        section_order,
        followers_dest_set,
        boss_shuffle_active,
    )
    for section in ALL_LOCATION_OUTPUT_SECTIONS:
        out[section] = location_sections.get(section, {})

    if followers and follower_shuffle_active:
        # Reorder by destination value
        canonical_dest_order = list(FOLLOWER_DESTINATION_MAP.values())
        ordered_followers: "dict[str, str]" = {}
        for dest in canonical_dest_order:
            for k, v in followers.items():
                if v == dest and k not in ordered_followers:
                    ordered_followers[k] = v
                    break
        # Append any not matched
        for k, v in followers.items():
            if k not in ordered_followers:
                ordered_followers[k] = v
        out["Followers"] = ordered_followers

    drops = _emit_drops(data)
    if drops:
        out["Drops"] = drops

    prize_packs = _emit_prize_packs(data)
    if prize_packs:
        out["PrizePacks"] = prize_packs

    if entrance_shuffle_active:
        out["Entrances"] = _emit_entrances(data, key_to_category, category_order)
    out["meta"] = _emit_meta(data)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=4, ensure_ascii=False)


def _cli(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: transformer_v2.py <input.json> <output.json>", file=sys.stderr)
        return 2
    transform(argv[1], argv[2])
    print(f"wrote {argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
