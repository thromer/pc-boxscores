#!/usr/bin/env python3

# TODO (for current season): Don't update if nothing changed.

import argparse
import re
import sys
import time
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING, TypedDict, cast

import bs4
import flask
import requests
from google.api_core import exceptions
from google.cloud import firestore_v1 as firestore
from google.cloud.firestore import DocumentSnapshot, Transaction
from google.cloud.firestore_v1 import Client as FirestoreClient


if TYPE_CHECKING:
    from collections.abc import Iterable

    from google.cloud.firestore_v1.base_document import BaseDocumentReference


LEAGUE_ID = "256"  # The Show
CONTENT_TYPE = "text/html; charset=utf-8"
PAST_STANDINGS_URL = (
    f"https://www.pennantchase.com/lgPastStandings.aspx?lgId={LEAGUE_ID}"
)

app = flask.Flask(__name__)


class NewgamesError(Exception):
    pass


class GameDoc(TypedDict):
    year: int
    day: int
    away: str
    home: str
    away_r: int
    home_r: int


@firestore.transactional  # pyright: ignore[reportUnknownMemberType]
def write_new_document(
    transaction: Transaction, ref: BaseDocumentReference, doc: GameDoc
) -> None:
    transaction.create(ref, dict(doc))


def equal_except_year(a: GameDoc, b: GameDoc) -> bool:
    a2 = a.copy()
    b2 = b.copy()
    _ = a2.pop("year", None)
    _ = b2.pop("year", None)
    return a2 == b2


def get_pc_year() -> int:
    r = requests.get(
        f"https://www.pennantchase.com/lgHistory.aspx?lgid={LEAGUE_ID}", timeout=60.0
    )
    r.raise_for_status()
    soup = bs4.BeautifulSoup(r.content, "html.parser")
    last_wsc = soup.find("p")
    if last_wsc is None:
        msg = "p element not found"
        raise NewgamesError(msg)
    last_year_str, rest = last_wsc.get_text().split(" ", 1)
    if not rest.startswith("World Series Champion"):
        msg = f"Couldn't determine year from {last_wsc.get_text()}"
        raise NewgamesError(msg)
    pc_year = int(last_year_str) + 1
    print(f"{pc_year=}")
    return pc_year


class CurrentYear(TypedDict):
    year: int
    timestamp: datetime


def get_year_from_db_maybe_update(db: FirestoreClient, day: int, dry_run: bool) -> int:  # noqa: FBT001
    metadata = db.collection("metadata")
    ref = metadata.document("current_year")
    current = cast(CurrentYear | None, cast(DocumentSnapshot, ref.get()).to_dict())  # pyright: ignore[reportUnknownMemberType]

    # Trust DB if day is late enough. Kind of high risk but whatever.
    if day >= 8:  # noqa: PLR2004
        if not current:
            msg = f"{day=}: metadata.current_year not found in firestore"
            raise NewgamesError(msg)
        return current["year"]

    # Trust DB if day is early and timestamp in DB is recent.
    now = datetime.now(tz=UTC)
    if current and now - current["timestamp"] <= timedelta(days=7):
        return current["year"]

    # At this point it is an early day and timestamp is old. So it
    # should be the case that the season has rolled over at the DB is
    # behind PC.
    pc_year = get_pc_year()
    if current and pc_year != current["year"] + 1:
        msg = (
            f"{day=}, metadata.current_year={current}: "
            f"expected pc_year == db_year + 1 but "
            f"{pc_year=} db_year={current['year']}"
        )
        raise RuntimeError(msg)
    new_current = {"year": pc_year, "timestamp": now}
    if not dry_run:
        ref.set(new_current)  # pyright: ignore[reportUnknownMemberType]
    else:
        print(f"Dry run, would have set metadata.current_year={new_current}")
    return pc_year


def new_games_to_db(args: Iterable[str] = ()) -> flask.Response:  # noqa: C901,PLR0912,PLR0915
    p = argparse.ArgumentParser()
    _ = p.add_argument("-d", "--day", type=int, default=None, required=False)
    _ = p.add_argument("-y", "--year", type=int, default=None, required=False)
    _ = p.add_argument(
        "-l",
        "--limit",
        type=int,
        default=float("inf"),
        required=False,
        help="Process at most limit days",
    )
    _ = p.add_argument(
        "-k",
        "--keep_going",
        default=False,
        action="store_true",
        help="Keep looking beyond the latest 2 days that already have all games in db",
    )
    _ = p.add_argument(
        "-i",
        "--ignore_errors",
        default=False,
        action="store_true",
        help="Accumulate mismatched value errors instead of failing immediately",
    )
    _ = p.add_argument(
        "-f",
        "--force",
        default=False,
        action="store_true",
        help="Overwrite mismatched values if the only difference is the year",
    )
    _ = p.add_argument("-n", "--dry_run", default=False, action="store_true")
    _ = p.add_argument("--nodry_run", dest="dry_run", action="store_false")
    r = p.parse_args(args=args)
    day = cast(int, r.day)
    year = cast(int, r.year)
    limit = cast(int, r.limit)
    keep_going = cast(bool, r.keep_going)
    ignore_errors = cast(bool, r.ignore_errors)
    force = cast(bool, r.force)
    dry_run = cast(bool, r.dry_run)
    db = FirestoreClient(project="pennantchase-256")
    mydb = db.collection("mydb")

    if not day:
        r = requests.get(
            f"https://www.pennantchase.com/baseballleague/scoreboard?lgid={LEAGUE_ID}",
            timeout=60,
        )
        soup = bs4.BeautifulSoup(r.content, "html.parser")
        select_elts = soup.find_all(
            lambda tag: tag.has_attr("id") and tag["id"] == "wday"
        )
        if not select_elts:
            day = 0
        else:
            select = select_elts[0]
            day_elts = select.find_all(lambda tag: tag.has_attr("value"))
            if day_elts:
                day = max([int(cast(str, e["value"])) for e in day_elts])
            else:
                day = 0
                print(f"Starting from day {day}", file=sys.stdout)

    fully_processed_count = 0
    error_count = 0

    # for each day
    considered = 0
    while day >= 1 and considered < limit:
        if not year:
            year = get_year_from_db_maybe_update(db, day, dry_run)
            print(f"year from db: {year=}")
        considered += 1
        print(f"considering {day=}", file=sys.stdout)
        day_url = f"https://www.pennantchase.com/baseballleague/scoreboard?lgid={LEAGUE_ID}&scoreday={day}"
        r = requests.get(day_url, timeout=60.0)
        r.raise_for_status()
        soup = bs4.BeautifulSoup(r.content, "html.parser")
        score_tables = soup.find_all(
            lambda tag: tag.get("class", "") == ["scoreTable", "table"]
        )

        score_count = len(score_tables)
        if score_count == 0:
            time.sleep(5)

        upload_count = 0
        #  for each game
        for score_table in score_tables:
            rows = score_table.select("tr")
            header = [c.get_text() for c in rows[0]]
            if header != [
                "Final",
                "1",
                "2",
                "3",
                "4",
                "5",
                "6",
                "7",
                "8",
                "9",
                "x",
                "R",
                "H",
                "E",
            ]:
                msg = f"Bad header {header}"
                raise NewgamesError(msg)
            if len(rows) < 3:  # noqa: PLR2004
                msg = "Box score missing rows"
                raise NewgamesError(msg)
            away_home_raw = rows[1:3]
            away_home_ids: list[str] = []
            away_home_runs: list[int] = []
            for line_raw in away_home_raw:
                line_elts = line_raw.select("td")
                if len(line_elts) != len(header):
                    msg = f"Line score line too short: {line_raw}"
                    raise NewgamesError(msg)
                team_id: str | None = None
                anchor = line_elts[0].select_one("a")
                if anchor is not None:
                    href = cast(str, anchor["href"])
                    m = re.match(r".*tid=([^&]+)", href)
                    if m is not None:
                        team_id = m[1]
                if team_id is None:
                    msg = f"team id not found in line score: {line_raw!r}"
                    raise NewgamesError(msg)
                away_home_ids.append(team_id)
                away_home_runs.append(int(line_elts[11].get_text()))
            game_id: str | None = None
            anchor = rows[-1].select_one("a")
            if anchor is not None:
                box_score_url = "https://www.pennantchase.com/" + cast(
                    str, anchor["href"]
                )
                m = re.match(r".*sid=([^&]+)", box_score_url)
                if m is not None:
                    game_id = m[1]
            if game_id is None:
                msg = "game id not found"
                raise NewgamesError(game_id)
            document: GameDoc = {
                "year": year,
                "day": day,
                "away": away_home_ids[0],
                "home": away_home_ids[1],
                "away_r": away_home_runs[0],
                "home_r": away_home_runs[1],
            }
            if not dry_run:
                wrote = False
                transaction = db.transaction()
                ref = mydb.document(game_id)
                try:
                    write_new_document(transaction, ref, document)
                    wrote = True
                    upload_count += 1
                    print("wrote", game_id)
                except exceptions.AlreadyExists:
                    print(game_id, "already exists")
                # Check if document is in db. This is here in case game_id
                # turns out not to be unique or if there is a bug.
                db_dict = cast(
                    GameDoc | None,
                    cast(DocumentSnapshot, ref.get()).to_dict(),  # pyright: ignore[reportUnknownMemberType]
                )
                if document != db_dict:
                    # TODO: would be nice to do this stuff transactionally
                    if force and (
                        db_dict is None or equal_except_year(document, db_dict)
                    ):
                        print(f"Overwriting year={document['year']} in {db_dict}")
                        ref.set(dict(document))  # pyright: ignore[reportUnknownMemberType]
                    else:
                        error_count += 1
                        # The "Wrote" case should be impossible
                        message = (
                            f"{game_id}: {'Wrote' if wrote else 'Tried to write'} "
                            f"{document} but db contains {db_dict}"
                        )
                        if ignore_errors:
                            print(message)
                        else:
                            raise ValueError(message)
            else:
                print(f"Dry run, would have tried writing {game_id}: {document}")

        if score_count > 0 and upload_count == 0:
            print(f"already processed {day=}", file=sys.stdout)
            fully_processed_count += 1
            if fully_processed_count > 1 and not keep_going:
                print(f"already processed {fully_processed_count} days, stopping")
                break

        day -= 1

    if error_count > 0:
        msg = f"{error_count} games with database mismatches"
        raise RuntimeError(msg)
    return flask.Response(status=HTTPStatus.OK)


@app.route("/", methods=["POST"])
def new_games_to_db_service() -> flask.Response:
    try:
        response = new_games_to_db()
    except NewgamesError as e:
        response = flask.Response(status=HTTPStatus.BAD_REQUEST, response=str(e))
    return response


if __name__ == "__main__":
    _ = new_games_to_db(sys.argv[1:])
