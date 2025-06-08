#!/usr/bin/env python

import os
import sys

port = os.environ.get('PORT', '8080')
cmd = [
    'gunicorn', 
    f'--bind=:{port}', 
    '--workers=1', 
    '--threads=8', 
    '--timeout=0',
    # '--log-level=debug',
    'main:app',
]
print(f'running gunicorn args={cmd}', file=sys.stderr)
os.execvp('gunicorn', cmd)
