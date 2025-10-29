#!/usr/bin/env python3

import bs4


with open("RECORD-EXAMPLE", "r") as f:
    content = f.read()
    soup = bs4.BeautifulSoup(content, "html.parser")

    batting, pitching = soup.find_all("table")
    for label, table in (("BATTING", batting), ("PITCHING", pitching)):
        print("\n\n%s\n\n" % label)
        rows = table.find_all("tr")
        for row in [list(r) for r in rows[1:]]:
            cell = row[1]
            print(cell.find_all("a")[0]["href"])
