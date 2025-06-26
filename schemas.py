from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class ModeRead(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    active: Optional[bool] = True

    class Config:
        from_attributes = True


class ArchetypeRead(BaseModel):
    id: int
    name: str
    modes: List[ModeRead] = []

    class Config:
        from_attributes = True


class RoleRead(BaseModel):
    roleId: str
    roleName: str

    class Config:
        from_attributes = True


class RaceRead(BaseModel):
    id: int
    raceActive: Optional[bool] = True
    raceRoom: Optional[str] = None
    seed: Optional[str] = None

    class Config:
        from_attributes = True


class ScheduledRaceRead(BaseModel):
    id: int
    time: datetime
    season: int
    mode: int
    raceId: Optional[int] = None
    mode_obj: ModeRead
    race: Optional[RaceRead] = None

    class Config:
        from_attributes = True

class ScheduledRaceWrite(BaseModel):
    time: datetime
    season: int
    mode: int

class PingableModeRoleRead(BaseModel):
    modeId: int
    role: RoleRead

    class Config:
        from_attributes = True


class PingableArchetypeRoleRead(BaseModel):
    archetypeId: int
    role: RoleRead

    class Config:
        from_attributes = True


class SaviorRoleRead(BaseModel):
    archetypeId: int
    role: RoleRead

    class Config:
        from_attributes = True


class SettingRead(BaseModel):
    name: str
    value: str
    type: str

    class Config:
        from_attributes = True


class SettingWrite(BaseModel):
    name: str
    value: str
    type: str


class ScheduledRaceWrite(BaseModel):
    time: datetime
    season: int
    mode: int
    raceId: Optional[int] = None

    class Config:
        from_attributes = True


class SaviorRoleWrite(BaseModel):
    archetypeId: int
    roleId: str

    class Config:
        from_attributes = True
