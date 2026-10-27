import json
import re
from collections import Counter
from itertools import combinations
from pathlib import Path

GO = re.compile(r"(?<!\w)(?:go|golang)(?!\w)", re.I)


def load_rows(path):
    with Path(path).open(encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            if GO.search(row.get("name", "")):
                yield row


def pair_counts(rows):
    result = Counter()
    for row in rows:
        skills = sorted({str(skill).strip().lower() for skill in row.get("skills", []) if str(skill).strip()})
        result.update(combinations(skills, 2))
    return result


def encode(counter):
    return [{"skills": list(pair), "count": count} for pair, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))]

