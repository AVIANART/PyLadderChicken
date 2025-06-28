from sqlalchemy import ForeignKey, Text, Integer
from sqlalchemy.dialects.mysql import TINYINT, SMALLINT, BIT, BIGINT, TEXT, DATETIME
from sqlalchemy.orm import declarative_base, relationship, Mapped, mapped_column
from datetime import datetime
from typing import List, Optional

Base = declarative_base()


class Archetype(Base):
    __tablename__ = "archetypes"
    id: Mapped[int] = mapped_column(TINYINT, primary_key=True)
    name: Mapped[str] = mapped_column(TEXT, nullable=False)
    active: Mapped[Optional[bool]] = mapped_column(BIT, nullable=True, default=True)
    ladder: Mapped[Optional[bool]] = mapped_column(BIT, nullable=True, default=False)

    modes: Mapped[List["Mode"]] = relationship(
        back_populates="archetype_obj",
        primaryjoin="Archetype.id == foreign(Mode.archetype)",
    )
    pingableRoles: Mapped[List["PingableArchetypeRole"]] = relationship(
        back_populates="archetype"
    )
    saviorRoles: Mapped[List["SaviorRole"]] = relationship(back_populates="archetype")


class Mode(Base):
    __tablename__ = "modes"
    id: Mapped[int] = mapped_column(SMALLINT, primary_key=True)
    archetype: Mapped[int] = mapped_column(
        SMALLINT, ForeignKey("archetypes.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(TEXT, nullable=False)
    slug: Mapped[str] = mapped_column(TEXT, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    active: Mapped[Optional[bool]] = mapped_column(BIT, nullable=True, default=True)

    archetype_obj: Mapped["Archetype"] = relationship(back_populates="modes")
    pingableRoles: Mapped[List["PingableModeRole"]] = relationship(
        back_populates="mode"
    )
    scheduledRaces: Mapped[List["ScheduledRace"]] = relationship(
        back_populates="mode_obj"
    )


class Race(Base):
    __tablename__ = "races"
    id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    raceActive: Mapped[Optional[bool]] = mapped_column(BIT, nullable=True, default=True)
    raceRoom: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    seed: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)

    scheduledRace: Mapped["ScheduledRace"] = relationship(back_populates="race")
    partitionedRaces: Mapped[List["PartitionedRace"]] = relationship(
        back_populates="parentRace",
    )


class PartitionedRace(Base):
    __tablename__ = "partitionedRaces"
    id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    raceId: Mapped[int] = mapped_column(BIGINT, ForeignKey("races.id"), nullable=False)
    raceRoom: Mapped[Optional[str]] = mapped_column(
        TEXT, nullable=True, unique=True, index=True
    )

    parentRace: Mapped[Optional["Race"]] = relationship(
        back_populates="partitionedRaces"
    )


class Role(Base):
    __tablename__ = "roles"
    roleId: Mapped[str] = mapped_column(TEXT, nullable=False)
    roleName: Mapped[str] = mapped_column(TEXT, nullable=False, primary_key=True)

    pingableModeRoles: Mapped[List["PingableModeRole"]] = relationship(
        back_populates="role"
    )
    pingableArchetypeRoles: Mapped[List["PingableArchetypeRole"]] = relationship(
        back_populates="role"
    )
    pingableSaviorRoles: Mapped[List["SaviorRole"]] = relationship(
        back_populates="role"
    )


class PingableArchetypeRole(Base):
    __tablename__ = "pingableArchetypeRoles"
    archetypeId: Mapped[int] = mapped_column(
        TINYINT, ForeignKey("archetypes.id"), primary_key=True
    )
    roleId: Mapped[str] = mapped_column(
        TEXT, ForeignKey("roles.roleId"), primary_key=True
    )

    archetype: Mapped["Archetype"] = relationship(back_populates="pingableRoles")
    role: Mapped["Role"] = relationship(back_populates="pingableArchetypeRoles")


class PingableModeRole(Base):
    __tablename__ = "pingableModeRoles"
    modeId: Mapped[int] = mapped_column(
        SMALLINT, ForeignKey("modes.id"), primary_key=True
    )
    roleId: Mapped[str] = mapped_column(
        TEXT, ForeignKey("roles.roleName"), primary_key=True
    )

    mode: Mapped["Mode"] = relationship(back_populates="pingableRoles")
    role: Mapped["Role"] = relationship(back_populates="pingableModeRoles")


class SaviorRole(Base):
    __tablename__ = "saviorRoles"
    archetypeId: Mapped[int] = mapped_column(
        TINYINT, ForeignKey("archetypes.id"), primary_key=True
    )
    roleId: Mapped[str] = mapped_column(
        TEXT, ForeignKey("roles.roleId"), primary_key=True
    )

    archetype: Mapped["Archetype"] = relationship(back_populates="saviorRoles")
    role: Mapped["Role"] = relationship(back_populates="pingableSaviorRoles")


class ScheduledRace(Base):
    __tablename__ = "schedule"
    id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    time: Mapped[datetime] = mapped_column(DATETIME, nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    mode: Mapped[int] = mapped_column(SMALLINT, ForeignKey("modes.id"), nullable=False)
    raceId: Mapped[Optional[int]] = mapped_column(
        BIGINT, ForeignKey("races.id"), nullable=True
    )

    mode_obj: Mapped["Mode"] = relationship(back_populates="scheduledRaces")
    race: Mapped[Optional["Race"]] = relationship(back_populates="scheduledRace")


class Setting(Base):
    __tablename__ = "setting"
    name: Mapped[str] = mapped_column(
        Text, primary_key=True, index=True, nullable=False
    )
    value: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
