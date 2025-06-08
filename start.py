#!/usr/bin/env python

import os
import pwd
import sys

www_data = pwd.getpwnam('www-data')
os.setgroups([])
os.setgid(www_data.pw_gid)
os.setuid(www_data.pw_uid)

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
