#!/usr/bin/env python3

import argparse
import bs4
import firebase_admin
# import os
import re
import requests
# import sys

from firebase_admin import credentials, firestore
# from google.api_core import exceptions
# from pprint import pprint


if ('GOOGLE_APPLICATION_CREDENTIALS' not in os.environ and
    'FUNCTION_TARGET' not in os.environ and
    'FUNCTION_TRIGGER_TYPE' not in os.environ and
    ('CLOUD_SHELL' not in os.environ or not os.environ['CLOUD_SHELL'])):
  os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '../service-account-key.json'

LEAGUE_ID = '256'  # The Show

def another_thing():
  p = argparse.ArgumentParser()
  p.add_argument('-n', '--dry_run', default=False, action='store_true')
  p.add_argument('--nodry_run', dest='dry_run', action='store_false')
  r = p.parse_args()
  dry_run = r.dry_run
  
  if not dry_run:
    # Use the application default credentials
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {
      'projectId': 'pennantchase-256',
    })
    db = firestore.client()
    current_season_b = db.collection(u'current_season_leaders')
  
  for b, p in zip_longest(BATTING_DESCS, PITCHING_DESCS):
    bsk = b['sKey'] if b else None
    psk = p['sKey'] if p else None
    if bsk or psk:
      with open('SEASON-EXAMPLE-2', 'r') as f:
        content = f.read()
      soup = bs4.BeautifulSoup(content, 'html.parser')
      batting, pitching = [process_table(t) for t in soup.find_all('table')]
      if bsk:
        for k, v in batting.items():
          print(k, v['Name'], v['Year'], v['Team'], v['team_id'], v[b['sHeader']])
      if psk:
        for k, v in pitching.items():
          print(k, v['Name'], v['Year'], v['Team'], v['team_id'], v[p['sHeader']])
      
      url = single_season_url(LEAGUE_ID, bsk, psk)
      print(url)
      # TODO
      # r = requests.get(url)
      # r.raise_for_status()
    break # TODO
    continue # TODO
    bck = b['cKey'] if b else None
    pck = p['cKey'] if p else None
    if bck or pck:
      url = career_url(LEAGUE_ID, bck, pck)
      # print(url)
      r = requests.get(url)
      r.raise_for_status()
      soup = bs4.BeautifulSoup(r.content, 'html.parser')
      batting, pitching = soup.find_all('table')
      for label, table in (('BATTING',batting),('PITCHING',pitching)):
        rows = table.find_all('tr')
        for row in [list(r) for r in rows[1:]]:
          cell = row[1]
          print(label, cell.find_all('a')[0]['href'])

def main():
  another_thing()
  
if __name__ == '__main__':
  main()
