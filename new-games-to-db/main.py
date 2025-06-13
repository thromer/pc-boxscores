#!/usr/bin/env python3

# TODO (for current season): Don't update if nothing changed.

import argparse
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import bs4
import firebase_admin
import flask
import requests
from firebase_admin import credentials, firestore
from google.api_core import exceptions

LEAGUE_ID = '256'  # The Show
CONTENT_TYPE = 'text/html; charset=utf-8'
PAST_STANDINGS_URL = f'https://www.pennantchase.com/lgPastStandings.aspx?lgId={LEAGUE_ID}'

app = flask.Flask(__name__)

@firestore.transactional
def write_new_document(transaction, ref, data):
  transaction.create(ref, data)


def equal_except_year(a, b):
  a2 = a.copy()
  b2 = b.copy()
  if 'year' in a2:
    del a2['year']
  if 'year' in b2:
    del b2['year']
  return a2 == b2


def get_pc_year():
  r = requests.get(f'https://www.pennantchase.com/lgHistory.aspx?lgid={LEAGUE_ID}')
  r.raise_for_status()
  soup = bs4.BeautifulSoup(r.content, 'html.parser')
  last_wsc = soup.find('p')
  last_year_str, rest = last_wsc.text.split(' ', 1)
  if not rest.startswith('World Series Champion'):
    raise Exception(f"Couldn't determine year from {last_wsc.text}")
  pc_year = int(last_year_str) + 1
  print(f'{pc_year=}')
  return pc_year
  

def get_year_from_db_maybe_update(db: firestore.Client, day: int, dry_run: bool) -> int:
  metadata = db.collection(u'metadata')
  ref = metadata.document('current_year')
  current = ref.get().to_dict()

  # Trust DB if day is late enough. Kind of high risk but whatever.
  if day >= 8:
    if not current:
      raise Exception(f'{day=}: metadata.current_year not found in firestore')
    return current['year']

  # Trust DB if day is early and timestamp in DB is recent.
  now = datetime.now(tz=timezone.utc)
  if current and now - current['timestamp'] <= timedelta(days=7):
    return current['year']

  # At this point it is an early day and timestamp is old. So it should be the case that
  # the season has rolled over at the DB is behind PC.
  pc_year = get_pc_year()
  if current and pc_year != current['year'] + 1:
    raise Exception(f"{day=}, metadata.current_year={current}: expected pc_year == db_year + 1 but {pc_year=} db_year={current['year']}")
  new_current = {'year': pc_year, 'timestamp': now}
  if not dry_run:
    ref.set(new_current)
  else:
    print(f'Dry run, would have set metadata.current_year={new_current}')
  return pc_year
  

def new_games_to_db(args=[]):
  p = argparse.ArgumentParser()
  p.add_argument('-d', '--day', type=int, default=None, required=False)
  p.add_argument('-y', '--year', type=int, default=None, required=False)
  p.add_argument(
    '-l', '--limit', type=int, default=float('inf'), required=False,
    help='Process at most limit days')
  p.add_argument(
    '-k', '--keep_going', default=False, action='store_true',
    help='Keep looking beyond the latest two days that already have all games in db')
  p.add_argument(
    '-i', '--ignore_errors', default=False, action='store_true',
    help='Accumulate errors regarding mismatched values instead of failing immediately')
  p.add_argument(
    '-f', '--force', default=False, action='store_true',
    help='Overwrite mismatched values if the only difference is the year')
  p.add_argument('-n', '--dry_run', default=False, action='store_true')
  p.add_argument('--nodry_run', dest='dry_run', action='store_false')
  r = p.parse_args(args=args)
  day = r.day
  year = r.year
  limit = r.limit
  keep_going = r.keep_going
  ignore_errors = r.ignore_errors
  force = r.force
  dry_run = r.dry_run
  cred = credentials.ApplicationDefault()
  firebase_admin.initialize_app(cred, {
    'projectId': 'pennantchase-256',
  })
  db = firestore.client()
  mydb = db.collection(u'mydb')

  if not day:
    r = requests.get(f'https://www.pennantchase.com/baseballleague/scoreboard?lgid={LEAGUE_ID}')
    soup = bs4.BeautifulSoup(r.content, 'html.parser')
    select = soup.find_all(lambda tag: tag.has_attr('id') and tag['id'] == 'wday')[0]
    day_elts = select.find_all(lambda tag: tag.has_attr('value'))
    if day_elts:
      day = max([int(e['value']) for e in day_elts])
    else:
      day = 0
      print(f'Starting from day {day}', file=sys.stdout)

  fully_processed_count = 0
  error_count = 0
  
  # for each day
  considered = 0
  while day >= 1 and considered < limit:
    if not year:
      year = get_year_from_db_maybe_update(db, day, dry_run)
      print(f'year from db: {year=}')
    considered += 1
    print(f'considering {day=}', file=sys.stdout)
    day_url = f'https://www.pennantchase.com/baseballleague/scoreboard?lgid={LEAGUE_ID}&scoreday={day}'
    r = requests.get(day_url)
    r.raise_for_status()
    soup = bs4.BeautifulSoup(r.content, 'html.parser')
    score_tables = soup.find_all(lambda tag: tag.get('class','') == ['scoreTable', 'table'])

    score_count = len(score_tables)
    if score_count == 0:
      time.sleep(5)
      
    upload_count = 0
    #  for each game
    for score_table in score_tables:
      rows = score_table.find_all('tr')
      header = [c.text for c in rows[0]]
      if header != ['Final', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'x', 'R', 'H', 'E']:
        raise Exception(f'Bad header {header}')
      away_home_raw = rows[1:3]
      away_home_ids = []
      away_home_runs = []
      for line_raw in away_home_raw:
        # not very beautiful use of BeautifulSoup here:
        line_elts = list(line_raw)
        team_id = re.match(r'.*tid=([^&]+)', line_elts[0].find_all('a')[0]['href'])[1]
        away_home_ids.append(team_id)
        away_home_runs.append(int(line_elts[11].text))
        box_score_url = 'https://www.pennantchase.com/' + rows[-1].find_all('a')[0]['href']
        game_id = re.match(r'.*sid=([^&]+)', box_score_url)[1]

      # and since we have them handy
      # home_runs
      # away_runs
      # TODO really
      document = {
        u'year': year,
        u'day': day,
        u'away': away_home_ids[0],
        u'home': away_home_ids[1],
        u'away_r': away_home_runs[0],
        u'home_r': away_home_runs[1],
      }
      if not dry_run:
        wrote = False
        transaction = db.transaction()
        ref = mydb.document(game_id)
        try:
          write_new_document(transaction, ref, document)
          wrote = True
          upload_count += 1
          print('wrote', game_id)
        except exceptions.AlreadyExists as e:
          print(game_id, 'already exists')
          # Check if document is in db. This is here in case game_id
          # turns out not to be unique or if there is a bug.
        db_dict = ref.get().to_dict()
        if document != db_dict:
          # TODO would be nice to do this stuff transactionally
          if force and equal_except_year(document, db_dict):
            print(f"Overwriting year={document['year']} in {db_dict}")
            ref.set(document)
          else:
            error_count += 1
            # The "Wrote" case should be impossible
            message = f"{game_id}: {'Wrote' if wrote else 'Tried to write'} {document} but db contains {db_dict}"
            if ignore_errors:
              print(message)
            else:
              raise ValueError(message)
      else:
        print(f'Dry run, would have tried writing {game_id}: {document}')
        
    if score_count > 0 and upload_count == 0:
      print(f'already processed {day=}', file=sys.stdout)
      fully_processed_count += 1
      if fully_processed_count > 1 and not keep_going:
        print(f'already processed {fully_processed_count} days, stopping')
        break
      
    day -= 1

  if error_count > 0:
    raise Exception(f'{error_count} games with database mismatches')
  

@app.route('/', methods=['POST'])
def new_games_to_db_service():
  new_games_to_db()
  return ''


if __name__ == '__main__':
  new_games_to_db(sys.argv[1:])
