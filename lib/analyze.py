from collections import defaultdict

import bs4
import pprint
import re
import sys

BATTER_KEYS = ['AB', 'R', 'H', 'RBI', '2B', '3B', 'HR', 'BB', 'K', 'SH', 'SB', 'CS', 'E', 'D']
PITCHER_KEYS = ['OUT', 'H', 'HR', 'R', 'ER', 'BB', 'K', 'WP', 'HB', 'PC']

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
    player = {'Team': team}
    raw_name = re.sub('^\xa0+[a-z]+-', '', row[0])
    if raw_name.find(' ') > 0:
      player['Name'], player['Pos'] = raw_name.split(' ', 2)
    else:
      player['Name'] = raw_name
    for k, v in zip(headers[1:], row[1:]):
      player[k] = v
    players.append(player)
  return players

def analyze(data):
  messages = []
  soup = bs4.BeautifulSoup(data, 'html.parser')
  html_tables = soup.find_all('table')
  raw_tables = []
  for html_table in html_tables:
    raw_table = []
    for row in html_table.find_all('tr'):
      raw_row = []
      for cell in row.find_all('td'):
        raw_row.append(cell.text)
      raw_table.append(raw_row)
    raw_tables.append(raw_table)

  box_score_raw_table, batting_raw_table, pitching_raw_table = raw_tables

  lob_index = box_score_raw_table[0].index('LOB')

  # away home
  nicknames = [row[0] for row in box_score_raw_table[1:3]]
  opponents = {nicknames[i]: nicknames[1-i] for i in range(2)}
  lob = [int(row[lob_index]) for row in box_score_raw_table[1:3]]
  team_batting_totals = defaultdict(lambda: defaultdict(int))
  team_pitching_totals = defaultdict(lambda: defaultdict(int))
  batters = process_raw_table(batting_raw_table)
  pitchers = process_raw_table(pitching_raw_table)
  # pprint.pprint(batters)
  # pprint.pprint(pitchers)
  for batter in batters:
    for key in BATTER_KEYS:
      batter[key] = int(batter[key])
      team_batting_totals[batter['Team']][key] += batter[key]
    batter['1B'] = batter['H'] - batter['2B'] - batter['3B'] - batter['HR']
    batter['Opponent'] = opponents[batter['Team']]
    # messages.append('B %s %s %s %s %s %s %s %s' % (
    #    batter['Team'], batter['Name'], batter['AB'], batter['H'],
    #    batter['1B'], batter['2B'], batter['3B'], batter['HR']))
    if batter['1B'] > 0 and batter['2B'] > 0 and batter['3B'] > 0 and batter['HR'] > 0:
      messages.append('%s: %s hit for the cycle against the %s!' % (batter['Team'], batter['Name'], batter['Opponent']))
    if batter['HR'] >= 4:
        messages.append('%s: %s hit %d home runs against the %s!' % (
            batter['Team'], batter['Name'], batter['HR'], batter['Opponent']))
  for pitcher in pitchers:
    raw_ip = pitcher['IP']
    innings, thirds = re.match(r'^(\d*)\.([0-9])(?:\.|$)', raw_ip).groups()
    pitcher['OUT'] = int(innings) * 3 + int(thirds)
    # print(f"{innings=} {thirds=} {pitcher['OUT']=}")
    pitcher['Opponent'] = opponents[pitcher['Team']]
    for key in PITCHER_KEYS:
      pitcher[key] = int(pitcher[key])
      team_pitching_totals[pitcher['Team']][key] += pitcher[key]
    # messages.append('P %s %s' % (pitcher['Team'], pitcher['Name']))
    if pitcher['K'] >= 18:
        messages.append('%s: %s struck out %d batters against the %s!' % (pitcher['Team'], pitcher['Name'], pitcher['K'], pitcher['Opponent']))
  for index in range(2):
      pitching_index = index
      batting_index = 1 - index
      pitching_team = nicknames[pitching_index]
      batting_team = nicknames[batting_index]
      hit_count = team_batting_totals[batting_team]['H']
      if hit_count <= 0:
          pitchers_str = ' and '.join([p['Name'] for p in pitchers if p['Team'] == pitching_team])
          if (team_batting_totals[pitching_team]['E'] == 0 and
              lob[batting_index] == 0 and
              team_pitching_totals[pitching_team]['BB'] == 0 and
              team_pitching_totals[pitching_team]['HB'] == 0):
            game = 'perfect game'
          else:
            game = ('no-' if hit_count == 0 else '%d-' % hit_count) + 'hitter'
          messages.append('%s: %s threw a %s against the %s!' % (
              pitching_team, pitchers_str, game, batting_team))
  # messages.append(pprint.pformat(team_batting_totals))
  # messages.append(pprint.pformat(team_pitching_totals))
  return messages
