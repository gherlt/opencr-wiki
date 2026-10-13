"""Writes field descriptions into the field notes (docs/tooltips/*.md).

    python tools/apply_field_texts.py TEXTS.tsv TOOLTIPS_DIR DEFAULT_MD

TEXTS.tsv has the columns table, column, label, text. For each line, the
description ("Tooltip") cell of the field's row in the field notes is set.

- A table without a Tooltip column gets one (inserted after the column cell),
  so the technical Notes are never overwritten.
- A row that documents several fields at once is split: the field gets a row
  of its own (with its label and a copy of the notes), so every field keeps
  its own description.
- A table can have sections in several files (some are only cross-references);
  the row is looked for in all of them. A field without a row gets one in the
  table's section that has a table; a table without any section gets a new
  section at the end of DEFAULT_MD.
- Only files that really change are written, with their original line endings.
"""
import csv
import re
import sys
from pathlib import Path

HEADER = ["| Display label | Column | Tooltip | Notes |", "|---|---|---|---|"]
COLUMN_CELL_RE = re.compile(r"\s*`[^`]+`(?:\s*(?:,|/|&|and|or)?\s*`[^`]+`)*\s*")


def esc(text):
    return text.replace("|", "\\|").strip()


def cells_of(line):
    return line.strip().strip("|").split("|")


def join(cells):
    return "|" + "|".join(cells) + "|"


def table_blocks(lines, start, end):
    """Contiguous markdown tables in a section, as lists of line indexes."""
    blocks, cur = [], []
    for i in range(start, end):
        if lines[i].startswith("|"):
            cur.append(i)
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    return blocks


def ensure_tooltip_column(lines, block):
    """Inserts a Tooltip column after the Column column if the table has none."""
    header = [c.strip() for c in cells_of(lines[block[0]])]
    if "Tooltip" in header or "Column" not in header:
        return
    k = header.index("Column") + 1
    for n, i in enumerate(block):
        cells = cells_of(lines[i])
        cells.insert(k, " Tooltip " if n == 0 else "---" if n == 1 else " ")
        lines[i] = join(cells)


def main(texts_path, tooltips_dir, default_md):
    originals = {p: p.read_bytes().decode("utf-8") for p in Path(tooltips_dir).glob("*.md")}
    newline = {p: "\r\n" if "\r\n" in text else "\n" for p, text in originals.items()}
    files = {p: text.replace("\r\n", "\n").split("\n") for p, text in originals.items()}
    with open(texts_path, encoding="utf-8", newline="") as f:
        texts = list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))

    def sections(table):
        """All (path, start, end) of the table's sections, those with a table first."""
        found = []
        for path, lines in files.items():
            for i, line in enumerate(lines):
                if line.startswith(f"## Table `{table}`"):
                    end = next((j for j in range(i + 1, len(lines)) if lines[j].startswith("## ")), len(lines))
                    found.append((path, i, end))
        return sorted(found, key=lambda s: not any(x.startswith("|") for x in files[s[0]][s[1]:s[2]]))

    def set_in(lines, start, end, col, label, text):
        for block in table_blocks(lines, start, end):
            for i in block:
                cells = cells_of(lines[i])
                for j, cell in enumerate(cells):
                    if not (COLUMN_CELL_RE.fullmatch(cell) and f"`{col}`" in cell):
                        continue
                    ensure_tooltip_column(lines, block)
                    cells = cells_of(lines[i])
                    names = re.findall(r"`([^`]+)`", cells[j])
                    if len(names) > 1:  # split: the field gets a row of its own
                        own = list(cells)
                        if j > 0:
                            own[j - 1] = f" {label} "
                        own[j] = f" `{col}` "
                        own[j + 1] = f" {text} "
                        rest = [n for n in names if n != col]
                        cells[j] = " " + " / ".join(f"`{n}`" for n in rest) + " "
                        lines[i] = join(cells)
                        lines.insert(i + 1, join(own))
                    else:
                        cells[j + 1] = f" {text} "
                        # last field of a split row: replace the combined label
                        if j > 0 and re.search(r"/|,|\+", cells[j - 1]):
                            cells[j - 1] = f" {label} "
                        lines[i] = join(cells)
                    return True
        return False

    replaced = added = 0
    for t in texts:
        table, col, label, text = t["table"], t["column"], t["label"], esc(t["text"])
        secs = sections(table)
        # 1. set the description of an existing row, in any file
        if any(set_in(files[p], s, e, col, label, text) for p, s, e in secs):
            replaced += 1
            continue
        # 2. add a row to the table's best section
        if secs:
            path, start, end = secs[0]
            lines = files[path]
            blocks = table_blocks(lines, start, end)
            if not blocks:  # section without a table yet: start one at its end
                last = end - 1
                while last > start and (not lines[last].strip() or lines[last].strip() == "---"):
                    last -= 1
                lines[last + 1:last + 1] = ["", *HEADER]
                blocks = [[last + 2, last + 3]]
            block = blocks[-1]
            ensure_tooltip_column(lines, block)
            header = [c.strip() for c in cells_of(lines[block[0]])]
            row = [""] * len(header)
            k = header.index("Column") if "Column" in header else 1
            row[k - 1], row[k], row[k + 1] = label, f"`{col}`", text
            lines.insert(block[-1] + 1, "| " + " | ".join(row) + " |")
            added += 1
            continue
        # 3. no section anywhere: create one in the default file
        lines = files[Path(tooltips_dir) / default_md]
        if not any(line.startswith(f"## Table `{table}`") for line in lines):
            lines += ["", "---", "", f"## Table `{table}`", "", *HEADER]
        lines.append(f"| {label} | `{col}` | {text} | |")
        added += 1

    for path, lines in files.items():
        text = "\n".join(lines)
        if text != originals[path].replace("\r\n", "\n"):  # only files that really changed
            path.write_bytes(text.replace("\n", newline[path]).encode("utf-8"))
    print(f"{replaced} descriptions set, {added} rows added")


if __name__ == "__main__":
    main(*sys.argv[1:4])
