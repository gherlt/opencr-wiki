"""Extracts the field captions editors see from the PHPGenerator forms.

    python tools/extract_form_labels.py C:/xampp/open_ENG data/form_labels.tsv

Reads every <form>.php, splits it into its page classes, finds the table each
page edits (its TableDataset) and the captions of that page's edit columns.
Writes one row per (table, column) with all captions found, the most frequent
first, and the forms/pages they come from.
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

CLASS_RE = re.compile(r"^\s*class (\w+) extends (?:Page|DetailPage)\b", re.M)
DATASET_RE = re.compile(r"\$this->dataset = new TableDataset\(\s*[^,]+,\s*[^,]+,\s*'`([^`]+)`'\)")
EDIT_RE = re.compile(r"new (\w*EditColumn)\(\s*'([^']*)',\s*'([^']*)'")
TITLE_RE = re.compile(r"\$this->SetTitle\('([^']*)'\)")


def main(form_dir, out_file):
    captions = defaultdict(Counter)
    sources = defaultdict(set)
    titles = {}
    for path in sorted(Path(form_dir).glob("*.php")):
        text = path.read_text(encoding="utf-8", errors="replace")
        starts = [m for m in CLASS_RE.finditer(text)]
        for i, m in enumerate(starts):
            block = text[m.start(): starts[i + 1].start() if i + 1 < len(starts) else len(text)]
            ds = DATASET_RE.search(block)
            if not ds:
                continue
            table = ds.group(1)
            title = TITLE_RE.search(block)
            if title:
                titles.setdefault(table, Counter())[title.group(1)] += 1
            for _kind, caption, column in EDIT_RE.findall(block):
                captions[(table, column)][caption.strip()] += 1
                sources[(table, column)].add(f"{path.stem}:{m.group(1)}")
    with open(out_file, "w", encoding="utf-8", newline="\n") as out:
        out.write("table\tcolumn\tcaptions\tpage_titles\tsources\n")
        for (table, column), counter in sorted(captions.items()):
            caps = " | ".join(c for c, _ in counter.most_common())
            page_titles = " | ".join(t for t, _ in titles.get(table, Counter()).most_common())
            out.write(f"{table}\t{column}\t{caps}\t{page_titles}\t{len(sources[(table, column)])}\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
