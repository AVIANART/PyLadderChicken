from models import ScheduledRace
import app_context as ac

import random


def get_grabbag_mode_weights(sched_race: ScheduledRace) -> dict:
    grabbag_modes = ac.database_service.get_grabbag_enabled_modes()
    races = ac.database_service.get_seasons_grabbag_races(sched_race.season)
    decay_perc = float(ac.database_service.get_setting("grabbag_decay_percentage")) or 0.05

    grabbag_weights = {
        mode.id: max(0.01, 1.0 - decay_perc * sum(1 for race in races if race.rolledMode and race.rolledMode.id == mode.id))
        for mode in grabbag_modes
    }
    return grabbag_weights


def select_grabbag_mode_from_weights(grabbag_weights: dict) -> int:
    selection = random.choices(
        population=list(grabbag_weights.keys()),
        weights=list(grabbag_weights.values()),
        k=1
    )[0]
    return selection

