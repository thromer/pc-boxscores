#!/usr/bin/env python3

import bs4


with open("ACTIVE-NOT-FA-RAW", "r") as f:
    content = f.read()
    soup = bs4.BeautifulSoup(content, "html.parser")

    batting, pitching = soup.find_all("table")
    for label, table in (("BATTING", batting), ("PITCHING", pitching)):
        rows = table.find_all("tr")
        for row in [list(r) for r in rows[1:]]:
            cell = row[1]
            print(label, cell.find_all("a")[0]["href"])
