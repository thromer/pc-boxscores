#!/usr/bin/env python

import os
import sys
from typing import TYPE_CHECKING, override

from gunicorn.app.base import BaseApplication

from main import app


if TYPE_CHECKING:
    from flask import Flask

port = os.environ.get("PORT", "8080")

options = {
    "bind": f":{port}",
    "workers": 1,
    "threads": 8,
    "timeout": 0,
    # "loglevel": "debug",
}


class StandaloneApplication(BaseApplication):
    def __init__(self, wsgi_app: Flask, opts: dict[str, str | int]) -> None:
        self.application = wsgi_app
        self.options = opts
        super().__init__()

    @override
    def load_config(self) -> None:
        config = {
            key: value
            for key, value in self.options.items()
            if key in self.cfg.settings
        }
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    @override
    def load(self) -> Flask:  # pyright: ignore[reportIncompatibleMethodOverride]
        return self.application


print(f"running gunicorn options={options}", file=sys.stderr)
StandaloneApplication(app, options).run()
