import asyncio
from typing import Any, Union

import aiohttp
from pydantic import BaseModel, Field
import services


class Beatmap(BaseModel):
    set_id: int
    map_id: int
    map_md5: str

    title: str
    title_unicode: str
    version: str
    artist: str
    artist_unicode: str
    creator: str
    creator_id: int

    stars: float
    od: float
    ar: float
    hp: float
    cs: float
    mode: int
    bpm: float
    max_combo: int

    submit_date: str
    approved_date: str
    latest_update: str

    hit_length: float
    drain: int

    plays: int
    passes: int
    favorites: int

    rating: float

    approved: int
    full_set_present: bool

    mods_diff: dict[str, Any] | None = None

    async def save_to_directory(self) -> None:
        """Saves a beatmap's .osu file to ragnarok."""
        path = services.RAGNAROK_OSU_PATH / f"{self.map_id}.osu"
        if not path.exists():
            async with aiohttp.ClientSession() as sess:
                async with sess.get(
                    f"https://osu.ppy.sh/web/osu-getosufile.php?q={self.map_id}",
                    headers={"user-agent": "osu!"},
                ) as req:
                    if not (resp := await req.text()):
                        services.logger.critical(
                            f"Couldn't fetch the .osu file of {self.map_id}. Maybe because api rate limit?"
                        )
                        return

                    with path.open("w+") as osu:
                        osu.write(resp)

                    services.logger.info(
                        f"Saved {self.map_id}.osu to {services.RAGNAROK_OSU_PATH!r}"
                    )

    async def save(self) -> None:
        ragnarok_approved = {4: 5, 3: 4, 2: 3, 1: 2}

        if self.approved in ragnarok_approved:
            self.approved = ragnarok_approved[self.approved]

        model_dump = self.model_dump()
        model_dump.pop("mods_diff")

        await services.database.execute(
            "INSERT INTO beatmaps (server, set_id, map_id, map_md5, title, title_unicode, "
            "version, artist, artist_unicode, creator, creator_id, stars, od, ar, hp, cs, "
            "mode, bpm, max_combo, submit_date, approved_date, latest_update, length, "
            "drain, plays, passes, favorites, rating, approved, full_set_present) "
            "VALUES ('bancho', :set_id, :map_id, :map_md5, :title, :title_unicode, :version, "
            ":artist, :artist_unicode, :creator, :creator_id, :stars, :od, :ar, :hp, :cs, "
            ":mode, :bpm, :max_combo, :submit_date, :approved_date, :latest_update, :hit_length, "
            ":drain, :plays, :passes, :favorites, :rating, :approved, :full_set_present)",
            model_dump,
        )

        asyncio.create_task(self.save_to_directory())

    @staticmethod
    async def ensure_full_set(_maps: list["Beatmap"]) -> list["Beatmap"]:
        """Ensures all the beatmaps, in the set, are present in the database."""
        # just take the first map, as they should all have the same
        # `full_set_present` value
        f_map = _maps[0]

        if f_map.full_set_present:
            return _maps

        maps = await Beatmap.from_api(set_id=f_map.set_id, disable_auto_save=True)
        assert type(maps) == list

        # the whole beatmap set is present, update field.
        if len(maps) == len(_maps):
            await services.database.execute(
                "UPDATE beatmaps SET full_set_present = 1 WHERE set_id = :set_id",
                {"set_id": f_map.set_id},
            )
            return _maps

        new_maps: list["Beatmap"] = []
        for map in maps:
            exists = (False, "")

            for rina_map in _maps:
                if rina_map.map_id == map.map_id:
                    exists = (True, rina_map.map_md5)
                    break

            if exists[0]:
                # compare beatmap hashes, and make sure the existed
                # beatmap is up to date.
                if exists[1] != map.map_md5:
                    # delete previous data
                    await services.database.execute(
                        "DELETE FROM beatmaps WHERE map_id = :map_id",
                        {"map_id": map.map_id},
                    )
                else:
                    continue

            # save beatmap
            await map.save()
            new_maps.append(map)

        # update previous maps, where the `full_set_present` value was set to false
        await services.database.execute(
            "UPDATE beatmaps SET full_set_present = 1  "
            "WHERE set_id = :set_id AND full_set_present = 0 ",
            {"set_id": f_map.set_id},
        )
        services.logger.info(
            f"Saved {len(maps) - len(_maps)} beatmaps, so the full set is in the database."
        )

        _maps.extend(new_maps)
        return _maps

    @classmethod
    async def from_api(
        cls,
        map_id: int | None = None,
        set_id: int | None = None,
        map_md5: int | None = None,
        disable_auto_save: bool = False,
    ) -> Union[list["Beatmap"], "Beatmap", None]:
        if not (map_id or set_id):
            return

        params = (
            ("s", set_id) if set_id else ("b", map_id) if map_id else ("h", map_md5)
        )

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://osu.ppy.sh/api/get_beatmaps?{params[0]}={params[1]}&k={services.osu_key}"
            ) as req:
                if req.status != 200:
                    services.logger.warn(
                        f"beatmap (set_id: {set_id}, map_id: {map_id}) could not be found in the osu api."
                    )
                    return

                resp = await req.json()

                if set_id:
                    maps: list[Beatmap] = []
                    for map in resp:
                        child_map = Beatmap.from_api_mapping(map, present_set=True)
                        maps.append(child_map)

                        if not disable_auto_save:
                            # as the whole set is being saved, the full_set_present field, should be true.
                            await child_map.save()

                    maps.sort(key=lambda map: map.stars)

                    return maps

                map = Beatmap.from_api_mapping(resp)

                if not disable_auto_save:
                    await map.save()

                return map

    @classmethod
    async def from_sql(
        cls,
        set_id: int | None = None,
        map_id: int | None = None,
        map_md5: str | None = None,
    ) -> Union[list["Beatmap"], "Beatmap", None]:
        params = (
            ("set_id", set_id)
            if set_id
            else ("map_id", map_id) if map_id else ("map_md5", map_md5)
        )
        fetching_method = (
            services.database.fetch_all if set_id else services.database.fetch_one
        )

        data = await fetching_method(
            "SELECT set_id, map_id, map_md5, title, title_unicode, version, artist, "
            "artist_unicode, creator, creator_id, stars, od, ar, hp, cs, mode, bpm, "
            "max_combo, approved, submit_date, approved_date, latest_update, length AS hit_length, "
            "drain, plays, passes, favorites, rating, full_set_present FROM beatmaps "
            f"WHERE {params[0]} = :param ORDER BY stars ASC",
            {"param": params[1]},
        )

        if not data:
            return

        if not set_id:
            return cls(**dict(data))  # type: ignore

        return [cls(**dict(map)) for map in data]

    @classmethod
    def from_api_mapping(
        cls, resp: dict[str, str], present_set: bool = False
    ) -> "Beatmap":
        return cls(
            set_id=int(resp["beatmapset_id"]),
            map_id=int(resp["beatmap_id"]),
            map_md5=resp["file_md5"],
            title=resp["title"],
            title_unicode=resp["title_unicode"] or resp["title"],
            version=resp["version"],
            artist=resp["artist"],
            artist_unicode=resp["artist_unicode"] or resp["artist"],
            creator=resp["creator"],
            creator_id=int(resp["creator_id"]),
            stars=float(resp["difficultyrating"]),
            od=float(resp["diff_overall"]),
            ar=float(resp["diff_approach"]),
            hp=float(resp["diff_drain"]),
            cs=float(resp["diff_size"]),
            bpm=float(resp["bpm"]),
            mode=int(resp["mode"]),
            max_combo=0 if resp["max_combo"] is None else int(resp["max_combo"]),
            approved=int(resp["approved"]),
            submit_date=resp["submit_date"],
            approved_date="0" if not resp["approved_date"] else resp["approved_date"],
            latest_update=resp["last_update"],
            hit_length=float(resp["total_length"]),
            drain=int(resp["hit_length"]),
            plays=0,
            passes=0,
            favorites=0,
            rating=float(resp["rating"]),
            full_set_present=present_set,
        )
