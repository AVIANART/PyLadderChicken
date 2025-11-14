import asyncio
from enum import Enum
from dataclasses import dataclass
import requests
from typing import Optional, Dict, Any
import logging

import app_context as ac

MMMM_GEN_BODY = [
    {
        "preset": "custom",
        "weights": {
        "length": [
            -7,
            5
        ],
        "execution": [
            -2,
            8
        ],
        "familiarity": [
            -3,
            12
        ],
        "variance": [
            -5,
            10
        ]
        },
        "force": [
        "logic:noglitches"
        ],
        "veto": [
        "bombbag:on",
        "timer:timed-ohko",
        "shuffle:restricted",
        "shuffle:insanity",
        "door_shuffle:partitioned",
        "door_shuffle:crossed",
        "pottery:cave",
        "pottery:cavekeys"
        ],
        "race": True
    }
]


class AvianartGenStatus(Enum):
    """
    Enum representing the status of an avian art generation request.
    """

    PREGEN = "pregeneration"
    GENERATION = "generating"
    POSTGEN = "postgen"
    FAILURE = "failure"


@dataclass
class BasePatch:
    bps: Optional[str] = None


@dataclass
class SpoilerMeta:
    meta: Optional[Dict[str, Any]] = None


@dataclass
class Meta:
    startgen: Optional[int] = None
    gentime: Optional[int] = None


@dataclass
class AvianResponsePayload:
    hash: str
    message: str

    attempts: Optional[int] = None
    status: Optional[AvianartGenStatus] = None
    logic: Optional[str] = None
    patch: Optional[Dict] = None
    spoiler: Optional[SpoilerMeta] = None
    generated: Optional[str] = None
    size: Optional[int] = None
    vt: Optional[bool] = None
    basepatch: Optional[BasePatch] = None
    meta: Optional[Meta] = None
    fshash: Optional[str] = None
    starttime: Optional[int] = None
    gentime: Optional[int] = None
    type: Optional[str] = None
    bps_t0_p1: Optional[str] = None
    returnCode: Optional[int] = None


@dataclass
class AvianartGenPayload:
    status: int
    response: AvianResponsePayload


class AvianartService:
    """
    Service class for handling avian art generation requests.
    """

    def __init__(self, url: str, api_key: str):
        self.url = url
        self.api_key = api_key
        self.logger: logging.Logger = logging.getLogger("avianart")

    async def generate_seed(
        self, preset: str, race: bool, namespace: str = ""
    ) -> AvianartGenPayload:
        """
        Trigger seed generation from AVIANART.
        """

        self.logger.debug(
            f"Generating {'race' if race else ''}seed using {namespace}/preset: {preset}"
        )

        seed_params = {
            "race": race,
        }
        preset = preset.lower()
        if namespace:
            seed_params["namespace"] = namespace.lower()

        request_body = [{"args": seed_params}]
        generation_url = f"{self.url}?action=generate&preset={preset}"

        if preset == "mmmmavid23" or preset == "mmmmladder":
            request_body = MMMM_GEN_BODY
            generation_url = f"{self.url}?action=mystery"

        self.logger.debug(
            f"Request body for generation: {request_body} with preset: {preset}"
        )

        admin_role = ac.database_service.get_setting("admin_role_id")
        admin_ping = f"<@&{admin_role}> " if admin_role else ""

        try:
            generation_response = requests.post(
                generation_url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"{self.api_key}",
                },
                json=request_body,
            )
        except Exception as e:
            self.logger.error(
                f"Could not reach AVIANART: {e}"
            )
            await ac.discord_service.send_message(
                content=f"{admin_ping}Could not reach AVIANART:\n```{e}```",
            force_mention=True
            )
            return

        if generation_response.status_code != 200:
            self.logger.error(
                f"Failed to trigger seed generation using {namespace}/{preset}: {generation_response.text}"
            )
            await ac.discord_service.send_message(
                content=f"{admin_ping}Failed to trigger seed generation using {namespace}/{preset}:\n```{generation_response.text}```",
            force_mention=True
            )
            raise Exception(
                f"Failed to trigger seed generation using {namespace}/{preset}: {generation_response.text}"
            )

        seed_hash = generation_response.json()["response"].get("hash")

        generation_status = AvianartGenStatus.PREGEN
        while generation_status != AvianartGenStatus.FAILURE:
            await asyncio.sleep(5)
            status = await self.fetch_permalink(seed_hash)
            if not status.response.status:
                # Probably done???
                if status.response.patch:
                    self.logger.debug(
                        f"Generation completed for seed hash: {seed_hash}"
                    )
                    return status
            generation_status = status.response.status
            self.logger.debug(
                f"Current generation status for {seed_hash}: {generation_status}"
            )
        self.logger.error(
            f"Generation failed for seed hash: {seed_hash} with message: {status.response.message}"
        )
        await ac.discord_service.send_message(
            content=f"{admin_ping}Generation failed for seed hash: {seed_hash} with message:\n```{status.response.message}```",
            force_mention=True
        )

    async def fetch_permalink(self, seed_hash: str) -> AvianartGenPayload:
        """
        Fetch the permalink for a given seed hash.
        """
        self.logger.debug(f"Fetching permalink for seed hash: {seed_hash}")
        response = requests.get(
            f"{self.url}?action=permlink&hash={seed_hash}",
            headers={"Authorization": self.api_key},
        )

        if response.status_code != 200:
            self.logger.error(
                f"Failed to fetch permalink for {seed_hash}: {response.text}"
            )
            raise Exception(
                f"Failed to fetch permalink for {seed_hash}: {response.text}"
            )

        data = response.json()
        return AvianartGenPayload(
            status=data["status"], response=AvianResponsePayload(**data["response"])
        )
