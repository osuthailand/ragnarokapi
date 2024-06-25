from enum import IntEnum


class Approved(IntEnum):
    GRAVEYARD = -2
    WIP = -1
    PENDING = 0

    RANKED = 2
    APPROVED = 3
    QUALIFIED = 4
    LOVED = 5

    @property
    def has_leaderboard(self) -> bool:
        return self.value in (self.RANKED, self.APPROVED, self.QUALIFIED, self.LOVED)

    @property
    def awards_pp(self) -> bool:
        return self.value in (self.RANKED, self.APPROVED)
