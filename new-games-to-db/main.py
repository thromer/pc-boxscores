#!/usr/bin/env python3

# TODO (for current season): Don't update if nothing changed.

import argparse
import bs4
import firebase_admin
import os
import re
import requests
import sys
import time

from firebase_admin import credentials, firestore
from google.api_core import exceptions
from pprint import pprint


LEAGUE_ID = '256'  # The Show
BUCKET = 'pc256-box-scores'
CONTENT_TYPE = 'text/html; charset=utf-8'
PAST_STANDINGS_URL = f'https://www.pennantchase.com/lgPastStandings.aspx?lgId={LEAGUE_ID}'

@firestore.transactional
def write_new_document(transaction, ref, data):
  transaction.create(ref, data)

def new_games_to_db(request):
  p = argparse.ArgumentParser()
  p.add_argument('-d', '--day', type=int, default=None, required=False)
  p.add_argument('-y', '--year', type=int, default=None, required=False)
  p.add_argument('-l', '--limit', type=int, default=float('inf'), required=False)
  p.add_argument('-k', '--keep_going', default=False, action='store_true')
  p.add_argument('-n', '--dry_run', default=False, action='store_true')
  p.add_argument('--nodry_run', dest='dry_run', action='store_false')
  r = p.parse_args()
  day = r.day
  year = r.year
  limit = r.limit
  keep_going = r.keep_going
  dry_run = r.dry_run
  if not dry_run:
    # Use the application default credentials
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

  if not year:
    # TODO hope that if we're in playoffs we get the year right!
    r = requests.get(f'https://www.pennantchase.com/lgSchedule.aspx?lgid={LEAGUE_ID}')
    playoffs = r.content.decode().find('Playoff') >= 0
      
    r = requests.get(PAST_STANDINGS_URL)
    r.raise_for_status()
    last_year_str = re.sub(r"^.*Last Year's Standings: ([0-9]+)[^0-9].*$", r'\1', r.content.decode(), flags=re.DOTALL)
    if not re.match(r'^[0-9]+$', last_year_str):
      raise Exception("Couldn't determine year")
    last_year = int(last_year_str)
    year = last_year + (0 if playoffs else 1)
  print(f'{year=}', file=sys.stdout)

  fully_processed_count = 0

  # for each day
  considered = 0
  while day >= 1 and considered < limit:
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
        # Check if document is in db. This is here in case game_id turns out not to be unique.
        db_dict = ref.get().to_dict()
        if document != db_dict:
          raise ValueError(f"{game_id}: {'Wrote' if wrote else 'Tried to write'} {document} but db contains {db_dict}")
      else:
        print(f'Dry run, would have tried writing {game_id}: {document}')
      
    if score_count > 0 and upload_count == 0:
      print(f'already processed {day=}', file=sys.stdout)
      fully_processed_count += 1
      if fully_processed_count > 1 and not keep_going:
        print(f'already processed {fully_processed_count} days, stopping')
        break
    
    day -= 1
  return ''


if __name__ == '__main__':
    new_games_to_db(None)
