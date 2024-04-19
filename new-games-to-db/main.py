#!/usr/bin/env python3

# TODO (for current season): Don't update if nothing changed.

# gcloud --project pennantchase-256 functions deploy --gen2 --region us-central1 new_games_to_db --runtime python312 --trigger-http

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

if ('GOOGLE_APPLICATION_CREDENTIALS' not in os.environ and
    'FUNCTION_TARGET' not in os.environ and
    'FUNCTION_TRIGGER_TYPE' not in os.environ and
    ('CLOUD_SHELL' not in os.environ or not os.environ['CLOUD_SHELL'])):
  os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '../service-account-key.json'


LEAGUE_ID = '256'  # The Show
BUCKET = 'pc256-box-scores'
CONTENT_TYPE = 'text/html; charset=utf-8'
PAST_STANDINGS_URL = 'https://www.pennantchase.com/lgPastStandings.aspx?lgId=%s' % LEAGUE_ID

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
    r = requests.get('https://www.pennantchase.com/lgScoreboard.aspx?lgid=%s' % LEAGUE_ID)
    soup = bs4.BeautifulSoup(r.content, 'html.parser')
    select = soup.find_all(lambda tag: tag.has_attr('id') and tag['id'] == 'ContentPlaceHolder1_ddDays')[0]
    day = int(select.find_all(lambda tag: tag.has_attr('selected') and tag['selected'] == 'selected')[0].getText())
    print('Starting from day %d' % day, file=sys.stdout)

  if not year:
    # hope that if we're in playoffs we get the year right!
    r = requests.get('https://www.pennantchase.com/lgSchedule.aspx?lgid=%s' % LEAGUE_ID)
    playoffs = r.content.decode().find('Playoff') >= 0
      
    r = requests.get(PAST_STANDINGS_URL)
    r.raise_for_status()
    last_year_str = re.sub(r"^.*Last Year's Standings: ([0-9]+)[^0-9].*$", r'\1', r.content.decode(), flags=re.DOTALL)
    if not re.match('^[0-9]+$', last_year_str):
      raise Exception("Couldn't determine year")
    last_year = int(last_year_str)
    year = last_year + (0 if playoffs else 1)
  print('Year = %d' % year, file=sys.stdout)

  fully_processed_count = 0

  # for each day
  considered = 0
  while day >= 1 and considered < limit:
    considered += 1
    print('considering day %d' % day, file=sys.stdout)
    day_url = 'https://www.pennantchase.com/lgScoreboard.aspx?lgid=256&scoreday=%d' % day
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
        raise Exception('Bad header ' % header)
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
          raise ValueError('%s: %s %s but db contains %s' % (game_id, ('Wrote' if wrote else 'Tried to write'), document, db_dict))
      else:
        print('Dry run, would have tried writing %s: %s' % (game_id, document))
      
    if score_count > 0 and upload_count == 0:
      print('already processed day %d' % day, file=sys.stdout)
      fully_processed_count += 1
      if fully_processed_count > 1 and not keep_going:
        print('already processed %d days, stopping' % fully_processed_count)
        break
    
    day -= 1
  return ''


if __name__ == '__main__':
    new_games_to_db(None)
