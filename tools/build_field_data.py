"""Merges the sources of the field reference into one working table.

    python tools/build_field_data.py data CONFIG.json

Inputs in the data directory (never committed, see .gitignore):
  columns.tsv      live schema: information_schema.COLUMNS (read-only query)
  fks.tsv          live foreign keys: information_schema.KEY_COLUMN_USAGE
  form_labels.tsv  captions from the forms (tools/extract_form_labels.py)
  tooltips/*.md    field notes from open.cr_reports/docs/tooltips
Output: data/fields.tsv, one row per live column.
"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


TOOLTIP_TABLE_RE = re.compile(r"^## Table `([^`]+)`")
COLUMN_CELL_RE = re.compile(r"^`[^`]+`(?:\s*(?:,|/|&|and|or)?\s*`[^`]+`)*$")


def read_tsv(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def parse_tooltips(folder):
    """table -> column -> (display label, tooltip, notes) from the markdown tables."""
    notes = defaultdict(dict)
    for md in sorted(Path(folder).glob("*.md")):
        table = None
        for line in md.read_text(encoding="utf-8").splitlines():
            m = TOOLTIP_TABLE_RE.match(line)
            if m:
                table = m.group(1)
                continue
            if line.startswith("## "):
                table = None
            if not line.startswith("|") or line.startswith("|---"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            for i, cell in enumerate(cells):
                cols = re.findall(r"`([^`]+)`", cell)
                if cols and COLUMN_CELL_RE.match(cell) and i + 1 < len(cells):
                    label = cells[i - 1] if i > 0 else ""
                    tooltip = cells[i + 1]
                    rest = cells[i + 2] if i + 2 < len(cells) else ""
                    # The master-table sections of objects.md have no table header
                    # of their own; "objects" is the default there.
                    t = table or (md.stem if md.stem != "base-tables" else None)
                    if t:
                        for col in cols:
                            # Notes describing several columns at once are not
                            # reliable per column (e.g. a note on the month of a
                            # day/month/year group); keep them only for one.
                            notes[t].setdefault(col, (label, tooltip, rest if len(cols) == 1 else ""))
                    break
    return notes


def main(data_dir, config_path):
    data = Path(data_dir)
    # Form datasets that use another name than the live table (from the private configuration).
    aliases = json.load(open(config_path, encoding="utf-8")).get("form_table_aliases", {})
    columns = read_tsv(data / "columns.tsv")
    fks = {(r["TABLE_NAME"], r["COLUMN_NAME"]): (r["REFERENCED_TABLE_NAME"], r["REFERENCED_COLUMN_NAME"])
           for r in read_tsv(data / "fks.tsv")}
    labels = {}
    for r in read_tsv(data / "form_labels.tsv"):
        table = aliases.get(r["table"], r["table"])
        labels[(table, r["column"])] = r["captions"]
    tips = parse_tooltips(data / "tooltips")

    out_fields = ["table", "ord", "column", "type", "nullable", "key", "default", "extra",
                  "fk", "captions", "doc_label", "tooltip", "doc_notes"]
    with open(data / "fields.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_NONE, escapechar="\\")
        w.writerow(out_fields)
        for c in columns:
            t, col = c["TABLE_NAME"], c["COLUMN_NAME"]
            fk = fks.get((t, col))
            doc = tips.get(t, {}).get(col, ("", "", ""))
            w.writerow([t, c["ORDINAL_POSITION"], col, c["COLUMN_TYPE"], c["IS_NULLABLE"], c["COLUMN_KEY"],
                        c["COLUMN_DEFAULT"], c["EXTRA"], f"{fk[0]}.{fk[1]}" if fk else "",
                        labels.get((t, col), ""), *[x.replace("\t", " ") for x in doc]])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
