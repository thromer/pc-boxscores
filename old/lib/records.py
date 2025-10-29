#!/usr/bin/env python3

# TODO unclear what to do with ties? can't simply suppress because it
# isn't inevitable that they will overtake anyone. case in point is CG
# -- multiple n-way ties, suppressing would never tell you anything
# happened until you happen to rise up into a non-tie.  Kinda depends:
# low-n stats will have ties and won't have a lot of activity, so
# never suppress; high-n stats won't have a lot of ties so always
# suppress?

# TODO maybe (probably only affects averages e.g. ERA) -- have stats that sort order is reversed


# career https://www.pennantchase.com/lgHistoryCareer.aspx?sb=cCS&sp=cW&lgid=256
# single season example https://www.pennantchase.com/lgHistorySingleSeason.aspx?sb=history.cHR&sp=history.cW&tid=0&lgid=256
# current season https://www.pennantchase.com/lgStats.aspx?lgid=256&tid=0&roster=both&pitchers=0&position=0&stats=c&qual=no&lid=0&tag=0

# Let's have tuples for each of batting, pitching
# (our id, our label, pc career id, pc season id, season column header) later:  top_n_career, top_n_season, min_{various}, ...)

import argparse
import bs4
import firebase_admin
import itertools
import os
import pcweb
import re
import requests
# import sys

from collections import defaultdict
from firebase_admin import credentials, firestore

# from google.api_core import exceptions
from itertools import zip_longest
# from pprint import pprint

if (
    "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ
    and "FUNCTION_TARGET" not in os.environ
    and "FUNCTION_TRIGGER_TYPE" not in os.environ
    and ("CLOUD_SHELL" not in os.environ or not os.environ["CLOUD_SHELL"])
):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "../service-account-key.json"

LEAGUE_ID = "256"  # The Show

BATTING_TUPLES_LIST = [
    # key, inclSingle, label, cKey, sKey, sHeader, currHeader
    ("AVG", False, "Average", "AVG", "AVG", "Avg", "AVG"),  # Average
    ("OBP", False, "On Base", "OBP", "OBP", "OBP", "OBP"),  # Average
    ("SLG", False, "Slugging", "SLG", "SLG", "SLG", "SLG"),  # Average
    ("OPS", False, "OPS", "OPS", "OPS", "OPS", "OPS"),  # Average
    ("AB", True, "At Bats", "cAB", "history.cAB", "AB", "AB"),
    ("R", True, "Runs", "cR", "history.cR", "R", "Runs"),
    ("H", True, "Hits", "cH", "history.cH", "H", "Hits"),
    ("2B", True, "Doubles", "c2B", "history.c2B", "2B", "2B"),
    ("3B", True, "Triples", "c3B", "history.c3B", "3B", "3B"),
    ("HR", True, "Homers", "cHR", "history.cHR", "HR", "HR"),
    ("RBI", True, "RBI", "cRBI", "history.cRBI", "RBI", "RBI"),
    ("BB", True, "Walks", "cBB", "history.cBB", "BB", "BB"),
    ("K", True, "Strikeouts", "cK", "history.cK", "SO", "SO"),
    ("SB", True, "Stolen Bases", "cSB", "history.cSB", "SB", "SB"),
    ("CS", False, "Caught Stealing", "cCS", "history.cCS", "CS", None),  # Bad, boring
    ("SH", False, "Sac Hits", "cSacBunt", "history.cSacBunt", "SH", None),  # Boring
    ("SF", False, "Sac Fly", "cSacFly", "history.cSacFly", "SF", None),  # Boring
    ("HBP", True, "Hit By Pitch", "cHBP", "history.cHBP", "HBP", "HBP"),
    ("GDP", False, "GIDP", "cGDP", "history.cGDP", "GDP", "GDP"),  # Bad, boring
    (
        "E",
        False,
        "Errors",
        "cE",
        "history.cE",
        "E",
        None,
    ),  # Bad, boring (e.g. shortstop)
    ("DWAR", False, "D+/-", "cDWAR", "history.cDWAR", "D*", None),
]
for t in BATTING_TUPLES_LIST:
    if len(t) != 7:
        raise ValueError(t)
BATTING_DESCS = [
    {
        "key": x[0],  # Our key, stable
        "inclSingle": x[1],  # Include in single season records?
        "label": x[2],  # Friendly label, unstable
        "cKey": x[3],  # Key when scraping career
        "sKey": x[4],  # Key when scraping single-season
        "sHeader": x[5],  # Header in scraped single-season table
        "curHeader": x[6],  # Header in scraped current season
    }
    for x in BATTING_TUPLES_LIST
]

PITCHING_TUPLES_LIST = [
    # key, inclSingle, label, cKey, sKey, sHeader, currHeader
    ("G", False, "Games", "cG", "history.cG", "G", None),
    ("W", True, "Wins", "cW", "history.cW", "W", "Wins"),
    ("L", True, "Losses", "cL", "history.cL", "L", "Losses"),
    ("ERA_SP", False, "ERA (SP)", "ERA", None, None, None),  # Average
    ("ERA", False, "ERA", "ERAboth", "ERA", "ERA", "ERA"),  # Average
    ("WHIP_SP", False, "WHIP (SP)", "WHIP", None, None, None),  # Average
    ("WHIP", False, "WHIP", "WHIPboth", "WHIP", "WHIP", "WHIP"),  # Average
    ("IP", False, "Innings", "cIP", "history.cIP", "IP", None),
    ("HA", False, "Hits Allowed", "cHA", "history.cHA", "H", None),  # Bad / boring
    (
        "HR",
        True,
        "Homers Allowed",
        "cpHR",
        "history.cpHR",
        "HR",
        "HR Allowed",
    ),  # Bad / boring
    ("BB", True, "Walks", "cpBB", "history.cpBB", "BB", "Walks"),  # Bad
    ("K", True, "Strikeouts", "cpK", "history.cpK", "SO", "SO"),
    ("CG", True, "Complete Games", "cCG", "history.cCG", "CG", "CG"),
    ("SV", True, "Saves", "cSV", "history.cSV", "SV", "SV"),
    ("BS", True, "Blown Saves", "cBS", "history.cBS", "BS", "BS"),  # Bad / boring
    ("SHO", True, "Shutouts", "cSHO", "history.cSHO", "SHO", "SHO"),
    (
        "QS",
        False,
        "Quality Starts",
        "cQS",
        "history.cQS",
        "QS",
        None,
    ),  # Boring if you ask me
    ("WP", True, "Wild Pitch", "cWP", "history.cWP", "WP", "WP"),  # Bad / boring
    ("HB", False, "Hit Batters", "cHB", "history.cHB", "HB", None),  # Bad / boring
    ("H9_SP", False, "H/9 (SP)", "H9", None, None, None),  # Average
    ("H9", False, "H/9", "H9both", "H/9", "H/9", "H/9"),  # Average
    ("BB9_SP", False, "BB/9 (SP)", "BB9", None, None, None),  # Average, bad, boring
    ("BB9", False, "BB/9", "BB9both", "BB/9", "BB/9", "BB/9"),  # Average, bad, boring
    ("SO9_SP", False, "SO/9 (SP)", "SO9", None, None, None),  # Average
    ("SO9", False, "SO/9", "SO9both", "SO/9", "SO/9", "SO/9"),  # Average
    ("DICE", False, None, None, None, None, "DICE"),  # Average
]
for t in PITCHING_TUPLES_LIST:
    if len(t) != 7:
        raise ValueError(t)
PITCHING_DESCS = [
    {
        "key": x[0],  # Our key, stable
        "inclSingle": x[1],  # Include in single season records?
        "label": x[2],  # Friendly label, unstable
        "cKey": x[3],  # Key when scraping career
        "sKey": x[4],  # Key when scraping single-season
        "sHeader": x[5],  # Header in scraped single-season table
        "curHeader": x[6],  # Header in scraped current season
    }
    for x in PITCHING_TUPLES_LIST
]

# this is just for example
"""
STATS_URL = 'https://www.pennantchase.com/lgStats.aspx?lgid=256&tid=0&roster=both&pitchers=0&position=0&stats=c&qual=no&lid=0&tag=0'
def something():
  r = requests.get(STATS_URL)
  r.raise_for_status()
  data = r.content    
  soup = bs4.BeautifulSoup(data, 'html.parser')
  if batters:
    batting_table = find_table_by_id(soup, 'battingtable')
    b_result = process_table(batting_table, split_positions=True, link=link)
    if free_agents:
      free_b_r = requests.get(FREE_AGENT_BATTERS_URL_FMT % league_id)
      free_b_r.raise_for_status()
      free_b_data = free_b_r.content    
      free_b_soup = bs4.BeautifulSoup(free_b_data, 'html.parser')
      free_b_batting_table = find_table_by_id(free_b_soup, 'battingtable')
      free_b_result = process_table(free_b_batting_table, split_positions=True, link=link)
    else:
      free_b_result={'header': b_result['header'], 'rows': []}
    if b_result['header'] != free_b_result['header']:
      raise ValueError(f"Header mismatch {b_result['header']=} {free_b_result['header']=}")
    result = {'header': b_result['header'], 'rows': b_result['rows'] + free_b_result['rows']}

  if pitchers:
    pitching_table = find_table_by_id(soup, 'pitchingtable')
    result = process_table(pitching_table, split_positions=False, link=link)
    if free_agents:
      for role in (1,2):
        free_p_r = requests.get(FREE_AGENT_PITCHERS_URL_FMT % (role, league_id))
        free_p_r.raise_for_status()
        free_p_data = free_p_r.content    
        free_p_soup = bs4.BeautifulSoup(free_p_data, 'html.parser')
        free_p_pitching_table = find_table_by_id(free_p_soup, 'pitchingtable')
        free_p_result = process_table(free_p_pitching_table, split_positions=False, link=link)
        if result['header'] != free_p_result['header']:
          raise ValueError(f"Header mismatch {pformat(result['header'])=} {pformat(free_p_result['header'])=}")
        result['rows'] += free_p_result['rows']
"""


def build_url(url, league_id, b, p, args=None):
    args = args.copy() if args else []
    args.append("lgid=%s" % league_id)
    if b:
        args.append("sb=%s" % b)
    if p:
        args.append("sp=%s" % p)
    return url + ("" if not args else ("?" + "&".join(args)))


def career_url(league_id, b, p):
    return build_url(
        "https://www.pennantchase.com/lgHistoryCareer.aspx", league_id, b, p
    )


def single_season_url(league_id, b, p):
    return build_url(
        "https://www.pennantchase.com/lgHistorySingleSeason.aspx",
        league_id,
        b,
        p,
        args=["tid=0"],
    )


# TODO maybe refactor with process_raw_table in analyze.py
def process_raw_table(raw_table):
    headers = raw_table[0].copy()
    # Note: don't use the player text as a unique key. Hence we use an array not a map
    players = []
    for row in raw_table:
        if row[1:] == headers[1:]:
            team = row[0]
            continue
        if len(row) != len(headers):
            team = None  # a little hacky, we use this to avoid creating a pitcher named totals
            continue
        if not team:
            continue
        player = {"Team": team}
        raw_name = re.sub("^\xa0+[a-z]+-", "", row[0])
        if raw_name.find(" ") > 0:
            player["Name"], player["Pos"] = raw_name.split(" ", 2)
        else:
            player["Name"] = raw_name
        for k, v in zip(headers[1:], row[1:]):
            player[k] = v
        players.append(player)
    return players
    pass


def process_table(html_table):
    headers = None
    results = []
    for html_row in html_table.find_all("tr"):
        if not headers:
            headers = [cell.text for cell in html_row.find_all("td")]
            name_index = headers.index("Name")
            team_index = headers.index("Team")
            continue
        # row = [cell.text for cell in html_row.find_all('td')]
        name_cell = list(html_row)[name_index]
        player_href = name_cell.find_all("a")[0]["href"]
        player_id = re.search(
            r"(?:^|[^a-z0-9_-])id=([A-Fa-f0-9-]+)(?:$|&)", player_href
        )[1].upper()
        # print([c.text for c in html_row.find_all('td')])
        team_cell = list(html_row)[team_index]
        team_href = team_cell.find_all("a")[0]["href"]
        team_id = re.search(r"(?:^|[^a-z0-9_-])tid=([A-Fa-f0-9-]+)(?:$|&)", team_href)[
            1
        ].upper()
        result = {"player_id": player_id, "team_id": team_id}
        result.update(
            dict(zip(headers, [cell.text for cell in html_row.find_all("td")]))
        )
        result["Name"] = result["Name"].split("\xa0")[0]
        results.append(result)
    return results


def number(s):
    return float(s) if re.search(r"\.", s) else int(s)


def this_season_thing(db):
    p = argparse.ArgumentParser()
    p.add_argument("-n", "--dry_run", default=False, action="store_true")
    p.add_argument("--nodry_run", dest="dry_run", action="store_false")
    p.add_argument(
        "-y", "--year", type=int, default=None, required=True
    )  # TODO infer eventually?
    r = p.parse_args()
    year = r.year
    dry_run = r.dry_run

    current_season_b = db.collection("current_season_leaders_b")
    current_season_p = db.collection("current_season_leaders_p")

    descs_by_header_b = {
        "Leaders: " + d["curHeader"]: d for d in BATTING_DESCS if d["curHeader"]
    }
    descs_by_header_p = {
        "Leaders: " + d["curHeader"]: d for d in PITCHING_DESCS if d["curHeader"]
    }

    if dry_run:
        with open("CURRENT_SEASON", "r") as f:
            content = f.read()
            contents = [content, content, content]
    else:
        # TODO optimization -- the list of leagues *never* changes (at
        # least mid-season!) so we could cache this and save PC a request.
        contents = []
        url = "https://www.pennantchase.com/lgLeaders.aspx?lgid=%s&lid=0" % LEAGUE_ID
        r = requests.get(url)
        r.raise_for_status()
        content = r.content
        soup = bs4.BeautifulSoup(content, "html.parser")
        select = soup.find(
            lambda tag: tag.has_attr("id")
            and tag["id"] == "ContentPlaceHolder1_ddLeague"
        )
        lids = [o["value"] for o in select.find_all("option") if o["value"] != "0"]
        for lid in lids:
            url = "https://www.pennantchase.com/lgLeaders.aspx?lgid=%s&lid=%s" % (
                LEAGUE_ID,
                lid,
            )
            r = requests.get(url)
            r.raise_for_status()
            contents.append(r.content)

    p_unmerged = []
    b_unmerged = []
    for content in contents:
        soup = bs4.BeautifulSoup(content, "html.parser")
        html_tables = soup.find_all("table")

        b_result = {}
        p_result = {}

        # More robust would be to look up a player and see if they are a pitcher ...
        flavor = "batters"
        for html_table in html_tables:
            header = None
            # peeked = False
            list = []
            for html_row in html_table.find_all("tr"):
                if not header:
                    header = [cell.text for cell in html_row.find_all("th")][0]
                    # print('considering', header)
                    # TODO this is confusing and error prone.
                    if header in descs_by_header_b and flavor == "batters":
                        desc = descs_by_header_b[header]
                        result = b_result
                    else:
                        if header not in descs_by_header_p:
                            raise ValueError("switched back to batters %s" % header)
                        flavor = "pitchers"
                        desc = descs_by_header_p[header]
                        result = p_result
                    # print('flavor: %s stat: %s' % (flavor, desc['key']))
                    continue
                html_cells = html_row.find_all("td")
                value = number(html_cells[2].text)
                name_cell = html_cells[0]
                name_anchor = name_cell.find("a")
                href = name_anchor["href"]
                player_id = re.search(
                    r"(?:^|[^a-z0-9_-])id=([A-Fa-f0-9-]+)(?:$|&)", href
                )[1].upper()
                player_name = name_anchor.text
                team_name = name_cell.text.replace(player_name + ", ", "")
                # if not peeked:
                #  peeked = True
                #  print(team_name, player_id, player_name, value)
                list.append(
                    {
                        "player_id": player_id,
                        "value": value,
                        "Name": player_name,
                        "Team": team_name,
                        "Year": year,
                    }
                )
            # print('saving in ', 'presult' if result == p_result else 'bresult')
            # TODO again ugly, we could have saved some work and not done this ...
            if desc["inclSingle"]:
                result[desc["key"]] = list
            # if desc['key'] == 'K':
            #  print('bK', b_result.get('K'))
            #  print('pK', p_result.get('K'))
        b_unmerged.append(b_result)
        p_unmerged.append(p_result)

    # TODO again lots of duplication
    b_merged = {}
    p_merged = {}
    for k in b_unmerged[0].keys():
        # print('k',k)
        # print('hmm', b_unmerged[0][k])
        b_merged[k] = sorted(
            itertools.chain(*[u[k] for u in b_unmerged]),
            key=lambda x: (x["value"], x["player_id"]),
            reverse=True,
        )
    # print('\n b merged \n')
    # something went wrong with K before this point
    for k, v in b_merged.items():
        if not dry_run:
            new_val = {"values": v}
            doc_ref = current_season_b.document(k)
            doc_val = doc_ref.get()
            if not doc_val.exists or doc_val.to_dict() != new_val:
                doc_ref.set(new_val)
        else:
            print("\n", k)
            for player in v:
                print(player)
    for k in p_unmerged[0].keys():
        # print('k',k)
        # print('hmm', p_unmerged[0][k])
        p_merged[k] = sorted(
            itertools.chain(*[u[k] for u in p_unmerged]),
            key=lambda x: (x["value"], x["player_id"]),
            reverse=True,
        )
    # print('\n p merged \n')
    for k, v in p_merged.items():
        if not dry_run:
            new_val = {"values": v}
            doc_ref = current_season_p.document(k)
            doc_val = doc_ref.get()
            if not doc_val.exists or doc_val.to_dict() != new_val:
                doc_ref.set(new_val)
        else:
            print("\n", k)
            for player in v:
                print(player)


# populates off season collections ... JUST SINGLE SEASON. We should do career separately and refactor
def another_thing(db):
    p = argparse.ArgumentParser()
    p.add_argument("-n", "--dry_run", default=False, action="store_true")
    p.add_argument("--nodry_run", dest="dry_run", action="store_false")
    r = p.parse_args()
    dry_run = r.dry_run

    off_season_b = db.collection("off_season_single_season_leaders_b")
    off_season_p = db.collection("off_season_single_season_leaders_p")

    # TODO plenty of duplication here!
    for b, p in zip_longest(
        [bd for bd in BATTING_DESCS if bd["inclSingle"]],
        [pd for pd in PITCHING_DESCS if pd["inclSingle"]],
    ):
        bsk = b["sKey"] if b else None
        psk = p["sKey"] if p else None
        if bsk or psk:
            url = single_season_url(LEAGUE_ID, bsk, psk)
            print(url)
            r = requests.get(url)
            r.raise_for_status()
            # with open('SEASON-EXAMPLE-2', 'r') as f:
            #  content = f.read()
            soup = bs4.BeautifulSoup(r.content, "html.parser")
            batting, pitching = [process_table(t) for t in soup.find_all("table")]
            if bsk:
                values = []
                for v in batting:
                    # print(v['player_id'], v['Name'], v['Year'], v['Team'], v['team_id'], v[b['sHeader']])
                    value = {
                        "value": number(v[b["sHeader"]]),
                        "Year": number(v["Year"]),
                    }
                    value.update(
                        {k: v[k] for k in ["player_id", "Name", "Team", "team_id"]}
                    )
                    values.append(value)
                values.sort(
                    key=lambda x: (x["value"], x["Year"], x["player_id"]), reverse=True
                )
                if len(values) != 15:
                    raise ValueError("expected 15 entries in %s" % values)
                doc = {"values": values}
                if dry_run:
                    print(doc)
                else:
                    off_season_b.document(b["key"]).set(doc)
                    doc_ref = off_season_b.document(b["key"])
                    # print('supposedly wrote this somewhere', doc_ref.get().to_dict())

            if psk:
                values = []
                for v in pitching:
                    # print(v['player_id'], v['Name'], v['Year'], v['Team'], v['team_id'], v[p['sHeader']])
                    value = {
                        "value": number(v[p["sHeader"]]),
                        "Year": number(v["Year"]),
                    }
                    value.update(
                        {k: v[k] for k in ["player_id", "Name", "Team", "team_id"]}
                    )
                    values.append(value)
                values.sort(
                    key=lambda x: (x["value"], x["Year"], x["player_id"]), reverse=True
                )
                if len(values) != 15:
                    raise ValueError("expected 15 entries in %s" % values)
                doc = {"values": values}
                if dry_run:
                    print(doc)
                else:
                    off_season_p.document(p["key"]).set(doc)

        continue  # TODO

        bck = b["cKey"] if b else None
        pck = p["cKey"] if p else None
        if bck or pck:
            url = career_url(LEAGUE_ID, bck, pck)
            # print(url)
            r = requests.get(url)
            r.raise_for_status()
            soup = bs4.BeautifulSoup(r.content, "html.parser")
            batting, pitching = soup.find_all("table")
            for label, table in (("BATTING", batting), ("PITCHING", pitching)):
                rows = table.find_all("tr")
                for row in [list(r) for r in rows[1:]]:
                    cell = row[1]
                    print(label, cell.find_all("a")[0]["href"])


def add_rank(values, keyfn):
    """given a sorted list of dicts with value key, augment with rank and is_tied"""
    result = {}
    number_count = defaultdict(int)
    for v in values:
        number_count[v["value"]] += 1
    prev_number = -1
    prev_i = -1  # doesn't update if number == prev_number
    for i in range(len(values)):
        new_value = values[i].copy()
        number = new_value["value"]
        if number != prev_number:
            new_value["rank"] = i + 1
            prev_number = number
            prev_i = i
        else:
            new_value["rank"] = prev_i + 1
        new_value["tie"] = number_count[number] > 1
        result[keyfn(new_value)] = new_value
    return result


def merge_season_thing(db):
    PCWEB = pcweb.PcWeb("1000")
    # p = argparse.ArgumentParser()
    # p.add_argument('-n', '--dry_run', default=False, action='store_true')
    # p.add_argument('--nodry_run', dest='dry_run', action='store_false')
    # r = p.parse_args()
    # dry_run = r.dry_run

    off_season_b = db.collection("off_season_single_season_leaders_b")
    off_season_p = db.collection("off_season_single_season_leaders_p")
    current_season_b = db.collection("current_season_leaders_b")
    current_season_p = db.collection("current_season_leaders_p")
    live_season_b = db.collection("live_single_season_leaders_b")
    live_season_p = db.collection("live_single_season_leaders_p")

    # TODO again with the duplication!
    for desc in [d for d in BATTING_DESCS if d["inclSingle"]]:
        key = desc["key"]
        off = off_season_b.document(key).get().to_dict()["values"]
        off.sort(
            key=lambda x: (x["value"], x["Year"], x["player_id"]), reverse=True
        )  # TODO remove this is because i backfilled with wrong order at first also sorting doesn't really matter
        curr = current_season_b.document(key).get().to_dict()["values"]
        # print('curr',curr)
        # print('off',off)
        merged = sorted(
            off + curr,
            key=lambda x: (x["value"], x["Year"], x["player_id"]),
            reverse=True,
        )[: len(off)]
        new_merged_val = {"values": merged}
        old_live_ref = live_season_b.document(key)
        old_live_val = old_live_ref.get()
        # changed here
        if old_live_val.exists and old_live_val.to_dict() == new_merged_val:
            # nothing changed
            continue
        old_live = old_live_val.to_dict()["values"] if old_live_val.exists else []
        old_live_ref.set(new_merged_val)
        # to here
        if merged != old_live:
            print("\nFascinating, batting stat %s changed somehow" % key)
            old_live_ranked = add_rank(old_live, lambda x: (x["player_id"], x["Year"]))
            merged_ranked = add_rank(merged, lambda x: (x["player_id"], x["Year"]))
            # print('was')
            # for r in sorted(old_live_ranked.values(), key=lambda x: (x['value'],x['Year'],x['player_id']), reverse=True):
            #  print(r['rank'], r['tie'], r['Name'], r['Year'], r['value'])
            # print('is')
            # for r in sorted(merged_ranked.values(), key=lambda x: (x['value'],x['Year'],x['player_id']), reverse=True):
            #  print(r['rank'], r['tie'], r['Name'], r['Year'], r['value'])
            for k, v in merged_ranked.items():
                o = (
                    old_live_ranked[k]
                    if k in old_live_ranked
                    else {"rank": "N/A", "tie": "N/A", "value": "N/A"}
                )
                if (k not in old_live_ranked) or (v["rank"] < o["rank"]):
                    message = (
                        "%s: %s %s moved up from rank %s (tie %s) to rank %s (tie %s) val went from %s to %s"
                        % (
                            key,
                            v["Name"],
                            v["Year"],
                            o["rank"],
                            o["tie"],
                            v["rank"],
                            v["tie"],
                            o["value"],
                            v["value"],
                        )
                    )
                    print(message)
                    PCWEB.send_to_thromer("B %s season records change" % key, message)
            print("\n")
        # TODO actually compare to live_season_b and .set if changed

    for desc in [d for d in PITCHING_DESCS if d["inclSingle"]]:
        key = desc["key"]
        off = off_season_p.document(key).get().to_dict()["values"]
        off.sort(
            key=lambda x: (x["value"], x["Year"], x["player_id"]), reverse=True
        )  # TODO remove this is because i backfilled with wrong order at first also sorting doesn't really matter
        curr = current_season_p.document(key).get().to_dict()["values"]
        # print('curr',curr)
        # print('off',off)
        merged = sorted(
            off + curr,
            key=lambda x: (x["value"], x["Year"], x["player_id"]),
            reverse=True,
        )[: len(off)]
        new_merged_val = {"values": merged}
        old_live_ref = live_season_p.document(key)
        old_live_val = old_live_ref.get()
        if old_live_val.exists and old_live_val.to_dict() == new_merged_val:
            # nothing changed
            continue
        old_live = old_live_val.to_dict()["values"] if old_live_val.exists else []
        old_live_ref.set(new_merged_val)

        if merged != old_live:
            print("\nFascinating, pitching stat %s changed somehow" % key)
            old_live_ranked = add_rank(old_live, lambda x: (x["player_id"], x["Year"]))
            merged_ranked = add_rank(merged, lambda x: (x["player_id"], x["Year"]))
            # print('was')
            # for r in sorted(old_live_ranked.values(), key=lambda x: (x['value'],x['Year'],x['player_id']), reverse=True):
            #  print(r['rank'], r['tie'], r['Name'], r['Year'], r['value'])
            # print('is')
            # for r in sorted(merged_ranked.values(), key=lambda x: (x['value'],x['Year'],x['player_id']), reverse=True):
            #  print(r['rank'], r['tie'], r['Name'], r['Year'], r['value'])
            for k, v in merged_ranked.items():
                o = (
                    old_live_ranked[k]
                    if k in old_live_ranked
                    else {"rank": "N/A", "tie": "N/A", "value": "N/A"}
                )
                if (k not in old_live_ranked) or (v["rank"] < o["rank"]):
                    message = (
                        "%s: %s %s moved up from rank %s (tie %s) to rank %s (tie %s) val went from %s to %s"
                        % (
                            key,
                            v["Name"],
                            v["Year"],
                            o["rank"],
                            o["tie"],
                            v["rank"],
                            v["tie"],
                            o["value"],
                            v["value"],
                        )
                    )
                    print(message)
                    PCWEB.send_to_thromer("P %s season records change" % key, message)
            print("\n")


def main():
    # Use the application default credentials
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(
        cred,
        {
            "projectId": "pennantchase-256",
        },
    )
    db = firestore.client()
    # another_thing(db)
    this_season_thing(db)
    merge_season_thing(db)


if __name__ == "__main__":
    main()
