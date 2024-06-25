from enum import IntFlag, unique


@unique
class Playstyle(IntFlag):
    MOUSE = 1 << 0
    KEYBOARD = 1 << 1
    TABLET = 1 << 2
    TOUCH = 1 << 3
