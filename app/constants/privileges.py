from enum import IntFlag, unique


@unique
class Privileges(IntFlag):
    BANNED = 1 << 0

    USER = 1 << 1
    VERIFIED = 1 << 2

    SUPPORTER = 1 << 3

    BAT = 1 << 4
    MODERATOR = 1 << 5
    ADMIN = 1 << 6
    DEV = 1 << 7

    PENDING = 1 << 8
