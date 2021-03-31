#!/usr/bin/env python3

import os
import sys

from lib import analyze
from lib import pcweb

if ('GOOGLE_APPLICATION_CREDENTIALS' not in os.environ and
    'FUNCTION_TARGET' not in os.environ and
    'FUNCTION_TRIGGER_TYPE' not in os.environ and
    ('CLOUD_SHELL' not in os.environ or not os.environ['CLOUD_SHELL'])):
  os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = './service-account-key.json'

def main():
  data = sys.stdin.read()
  messages = analyze.analyze(data)
  if messages:
    print(' '.join(messages))
    pc = pcweb.PcWeb('1000')
    #pc.send_to_thromer('subject!', '\n'.join(messages))
  for message in messages:
    pc.league_chat('%s [Day %s]' % (message, 29), trailing_whitespace=4)
  

if __name__ == '__main__':
  main()

