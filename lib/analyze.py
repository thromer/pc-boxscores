import re
from dataclasses import dataclass, fields, replace

import bs4


NBSP = "\xa0"


@dataclass
class PlayerRecord:
    Name: str
    Team: str
    Opponent: str


@dataclass
class BatterRecord(PlayerRecord):
    Pos: str
    AB: int
    R: int
    H: int
    RBI: int
    Single: int
    Double: int
    Triple: int
    HR: int
    BB: int
    K: int
    SH: int
    SB: int
    CS: int
    E: int
    D: int


@dataclass
class PitcherRecord(PlayerRecord):
    OUT: int
    H: int
    HR: int
    R: int
    ER: int
    BB: int
    K: int
    WP: int
    HB: int
    PC: int


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
            player["Name"], player["Pos"] = raw_name.split(NBSP, 1)
        else:
            player["Name"] = raw_name
        players.append(player)
    return players


def make_batter(raw_batter: dict[str, str], opponents: dict[str, str]) -> BatterRecord:
    team = raw_batter["Team"]
    return BatterRecord(
        Name=raw_batter["Name"],
        Pos=raw_batter["Pos"],
        Team=team,
        Opponent=opponents[team],
        H=(h := int(raw_batter["H"])),
        Double=(double := int(raw_batter["2B"])),
        Triple=(triple := int(raw_batter["3B"])),
        HR=(hr := int(raw_batter["HR"])),
        Single=h - double - triple - hr,
        AB=int(raw_batter["AB"]),
        R=int(raw_batter["R"]),
        RBI=int(raw_batter["RBI"]),
        BB=int(raw_batter["BB"]),
        K=int(raw_batter["K"]),
        SH=int(raw_batter["SH"]),
        SB=int(raw_batter["SB"]),
        CS=int(raw_batter["CS"]),
        E=int(raw_batter["E"]),
        D=int(raw_batter["D"]),
    )


def make_pitcher(
    raw_pitcher: dict[str, str], opponents: dict[str, str]
) -> PitcherRecord:
    team = raw_pitcher["Team"]
    raw_ip = raw_pitcher["IP"]
    m = re.match(r"^(\d*)\.([0-9])(?:\.|$)", raw_ip)
    if not m:
        msg = "Innings pitched didn't match regex"
        raise BoxscoreError(msg)
    innings, thirds = m.groups()
    out = int(innings) * 3 + int(thirds)
    return PitcherRecord(
        Name=raw_pitcher["Name"],
        Team=team,
        Opponent=opponents[team],
        OUT=out,
        H=int(raw_pitcher["H"]),
        HR=int(raw_pitcher["HR"]),
        R=int(raw_pitcher["R"]),
        ER=int(raw_pitcher["ER"]),
        BB=int(raw_pitcher["BB"]),
        K=int(raw_pitcher["K"]),
        WP=int(raw_pitcher["WP"]),
        HB=int(raw_pitcher["HB"]),
        PC=int(raw_pitcher["PC"]),
    )


def get_team_batting_totals(batters: list[BatterRecord]) -> BatterRecord:
    int_names = [f.name for f in fields(BatterRecord) if f.type is int]
    return replace(
        batters[0],
        **{name: sum(getattr(b, name) for b in batters) for name in int_names},
        Name="",
        Pos="",
        Team="",
        Opponent="",
    )


def get_team_pitching_totals(pitchers: list[PitcherRecord]) -> PitcherRecord:
    int_names = [f.name for f in fields(PitcherRecord) if f.type is int]
    return replace(
        pitchers[0],
        **{name: sum(getattr(b, name) for b in pitchers) for name in int_names},
        Name="",
        Team="",
        Opponent="",
    )


@dataclass
class ProcessedData:
    nicknames: list[str]
    opponents: dict[str, str]
    lob: list[int]
    batters: list[BatterRecord]
    team_batting_totals: dict[str, BatterRecord]
    pitchers: list[PitcherRecord]
    team_pitching_totals: dict[str, PitcherRecord]


def process_data(data: str) -> ProcessedData:
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
    raw_batters = process_raw_table(batting_raw_table)
    raw_pitchers = process_raw_table(pitching_raw_table)
    batters = [make_batter(b, opponents) for b in raw_batters]
    team_batting_totals = {
        team: get_team_batting_totals([b for b in batters if b.Team == team])
        for team in nicknames
    }
    pitchers = [make_pitcher(b, opponents) for b in raw_pitchers]
    team_pitching_totals = {
        team: get_team_pitching_totals([p for p in pitchers if p.Team == team])
        for team in nicknames
    }
    return ProcessedData(
        nicknames,
        opponents,
        lob,
        batters,
        team_batting_totals,
        pitchers,
        team_pitching_totals,
    )


def analyze(data: str) -> list[str]:
    processed_data = process_data(data)
    messages: list[str] = []
    for batter in processed_data.batters:
        opponent = batter.Opponent
        if (
            batter.Single > 0
            and batter.Double > 0
            and batter.Triple > 0
            and batter.HR > 0
        ):
            messages.append(
                (  # noqa: UP034
                    f"{batter.Team}: {batter.Name} "
                    f"hit for the cycle against the {opponent}!"
                )
            )
        if batter.HR >= 4:  # noqa: PLR2004
            messages.append(
                (  # noqa: UP034
                    f"{batter.Team}: {batter.Name} "
                    f"hit {batter.HR} home runs against the {opponent}!"
                )
            )

    for pitcher in processed_data.pitchers:
        opponent = pitcher.Opponent
        if pitcher.K >= 18:  # noqa: PLR2004
            messages.append(
                (  # noqa: UP034
                    f"{pitcher.Team}: {pitcher.Name} "
                    f"struck out {pitcher.K} batters against the {opponent}"
                )
            )
    for index in range(2):
        pitching_index = index
        batting_index = 1 - index
        pitching_team = processed_data.nicknames[pitching_index]
        batting_team = processed_data.nicknames[batting_index]
        hit_count = processed_data.team_batting_totals[batting_team].H
        if hit_count <= 0:
            pitchers_str = " and ".join(
                [p.Name for p in processed_data.pitchers if p.Team == pitching_team]
            )
            if (
                processed_data.team_batting_totals[pitching_team].E == 0
                and processed_data.lob[batting_index] == 0
                and processed_data.team_pitching_totals[pitching_team].BB == 0
                and processed_data.team_pitching_totals[pitching_team].HB == 0
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
