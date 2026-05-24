import pprint
import re
from collections import defaultdict

import bs4


BATTER_KEYS = [
    "AB",
    "R",
    "H",
    "RBI",
    "2B",
    "3B",
    "HR",
    "BB",
    "K",
    "SH",
    "SB",
    "CS",
    "E",
    "D",
]
PITCHER_KEYS = ["OUT", "H", "HR", "R", "ER", "BB", "K", "WP", "HB", "PC"]

NBSP = "\xa0"


class BoxscoreError(Exception):
    pass


def process_raw_table(raw_table: list[list[str]]) -> list[dict[str, str]]:
    headers = raw_table[0].copy()
    # Note: don't use the player text as a unique key. Hence we use an array not a map
    players: list[dict[str, str]] = []
    team: str | None = None
    for row in raw_table:
        if row[1:] == headers[1:]:
            team = row[0]
            continue
        if len(row) != len(headers):
            team = None  # trick to avoid creating a pitcher named totals
            continue
        if not team:
            continue
        player = dict(zip(headers[1:], row[1:], strict=True))
        player["Team"] = team
        raw_name = re.sub("^\xa0+[a-z]+-", "", row[0])
        if raw_name.find(NBSP) > 0:
            player["Name"], player["Pos"] = raw_name.split(NBSP, 2)
        else:
            player["Name"] = raw_name
        players.append(player)
    return players


def analyze(data: str) -> list[str]:  # noqa: C901,PLR0912,PLR0915
    messages: list[str] = []
    soup = bs4.BeautifulSoup(data, "html.parser")
    html_tables = soup.select("table")
    raw_tables = [
        [
            [cell.get_text() for cell in row.select("td")]
            for row in html_table.select("tr")
        ]
        for html_table in html_tables[:3]
    ]
    if len(raw_tables) < 3:  # noqa: PLR2004
        msg = f"Expected at least 3 top-level tables, found {len(raw_tables)}"
        raise BoxscoreError(msg)

    box_score_raw_table, batting_raw_table, pitching_raw_table = raw_tables

    lob_index = box_score_raw_table[0].index("LOB")

    # away home
    nicknames = [row[0] for row in box_score_raw_table[1:3]]
    opponents = {nicknames[i]: nicknames[1 - i] for i in range(2)}
    lob = [int(row[lob_index]) for row in box_score_raw_table[1:3]]
    team_batting_totals = defaultdict[str, defaultdict[str, int]](
        lambda: defaultdict[str, int](int)
    )
    team_pitching_totals = defaultdict[str, defaultdict[str, int]](
        lambda: defaultdict[str, int](int)
    )
    batters = process_raw_table(batting_raw_table)
    pitchers = process_raw_table(pitching_raw_table)
    pprint.pprint(batters)
    pprint.pprint(pitchers)
    for batter in batters:
        stats = {key: int(batter[key]) for key in BATTER_KEYS}
        for key in BATTER_KEYS:
            team_batting_totals[batter["Team"]][key] += stats[key]
        stats["1B"] = stats["H"] - stats["2B"] - stats["3B"] - stats["HR"]
        opponent = opponents[batter["Team"]]
        if stats["1B"] > 0 and stats["2B"] > 0 and stats["3B"] > 0 and stats["HR"] > 0:
            messages.append(
                (  # noqa: UP034
                    f"{batter['Team']}: {batter['Name']} "
                    f"hit for the cycle against the {opponent}!"
                )
            )
        if stats["HR"] >= 4:  # noqa: PLR2004
            messages.append(
                (  # noqa: UP034
                    f"{batter['Team']}: {batter['Name']} "
                    f"hit {stats['HR']} home runs against the {opponent}!"
                )
            )

    for pitcher in pitchers:
        stats = {key: int(pitcher[key]) for key in PITCHER_KEYS}
        for key in PITCHER_KEYS:
            team_pitching_totals[pitcher["Team"]][key] += stats[key]
        # messages.append('P %s %s' % (pitcher['Team'], pitcher['Name']))
        raw_ip = pitcher["IP"]
        m = re.match(r"^(\d*)\.([0-9])(?:\.|$)", raw_ip)
        if not m:
            msg = "Innings pitch didn't match regex"
            raise RuntimeError(msg)
        innings, thirds = m.groups()
        stats: dict[str, int] = {}
        stats["OUT"] = int(innings) * 3 + int(thirds)
        # print(f"{innings=} {thirds=} {pitcher['OUT']=}")
        opponent = opponents[pitcher["Team"]]
        if stats["K"] >= 18:  # noqa: PLR2004
            messages.append(
                (  # noqa: UP034
                    f"{pitcher['Team']}: {pitcher['Name']}"
                    f"struck out {stats['K']} batters against the {opponent}"
                )
            )
    for index in range(2):
        pitching_index = index
        batting_index = 1 - index
        pitching_team = nicknames[pitching_index]
        batting_team = nicknames[batting_index]
        hit_count = team_batting_totals[batting_team]["H"]
        if hit_count <= 0:
            pitchers_str = " and ".join(
                [p["Name"] for p in pitchers if p["Team"] == pitching_team]
            )
            if (
                team_batting_totals[pitching_team]["E"] == 0
                and lob[batting_index] == 0
                and team_pitching_totals[pitching_team]["BB"] == 0
                and team_pitching_totals[pitching_team]["HB"] == 0
            ):
                game = "perfect game"
            else:
                game = ("no-" if hit_count == 0 else f"{hit_count}-") + "hitter"
            messages.append(
                (  # noqa: UP034
                    f"{pitching_team}: {pitchers_str} "
                    f"threw a {game} against the {batting_team}!"
                )
            )
    # messages.append(pprint.pformat(team_batting_totals))
    # messages.append(pprint.pformat(team_pitching_totals))
    return messages
