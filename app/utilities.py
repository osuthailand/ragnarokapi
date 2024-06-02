from fastapi.params import Query
from enum import IntEnum

class Gamemode(IntEnum):
    VANILLA = 0
    RELAX = 1

    @property
    def stats_table(self) -> str:
        return "stats_rx" if self == Gamemode.RELAX else "stats" 

class Mode(IntEnum):
    STANDARD = 0
    TAIKO = 1
    CATCH = 2
    MANIA = 3

    def to_db(self, field: str):
        """ Converts the fields name, thats depended on the mode, to match the current mode. """
        mode = ("std", "taiko", "catch", "mania")[self.value]
        return f"{field}_{mode}"


class ModeAndGamemode:
    def __init__(self) -> None:
        self.gamemode: Gamemode = Gamemode.VANILLA
        self.mode: Mode = Mode.STANDARD

    @classmethod
    def parse(cls, mode: int = Query(0), gamemode: int = Query(0)) -> "ModeAndGamemode":
        c = cls()

        if mode < 0 or mode > 3:
            c.mode = Mode.STANDARD
        else:
            c.mode = Mode(mode)

        if gamemode < 0 or gamemode > 1:
            c.gamemode = Gamemode.VANILLA
        else:
            c.gamemode = Gamemode(gamemode)

        # incompatible pair; reset.
        if c.gamemode == Gamemode.RELAX and c.mode == Mode.MANIA:
            c.gamemode = Gamemode.VANILLA
            c.mode = Mode.STANDARD

        return c


def parse_including_query(include: list[str] = Query([])) -> list[str]:
    # parses include query field as such:
    # 
    # ?include=[stats,clans] = ["stats", "clans"]
    # ?include=stats,clans = ["stats", "clans"]

    if not include:
        return []

    first_include = include[0]

    if first_include.startswith("[") and first_include.endswith("]"):
        first_include = first_include[1:len(first_include) - 1]

    all_inc = first_include.split(",")

    return all_inc