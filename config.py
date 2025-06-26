import dotenv

required_config = [
    "RACETIME_CATEGORY_SLUG",
    "RACETIME_CLIENT_ID",
    "RACETIME_CLIENT_SECRET",
    "DISCORD_TOKEN",
    "AVIANART_API_URL",
    "AVIANART_API_KEY",
    "DATABASE_URL",
    "DATABASE_NAME",
    "DATABASE_USER",
    "DATABASE_PASSWORD",
]


def import_config():
    _config = dotenv.dotenv_values()

    for key in required_config:
        if key not in _config or not _config[key]:
            raise ValueError(f"Missing required configuration: {key}")

    config = {key.lower(): _config.get(key) for key in _config}

    return config
