"""Writes field descriptions into the field notes (docs/tooltips/*.md).

    python tools/apply_field_texts.py TEXTS.tsv TOOLTIPS_DIR DEFAULT_MD

TEXTS.tsv has the columns table, column, label, text. For each line, the
description ("Tooltip") cell of the matching row in the field notes is
replaced. A row that lists several columns at once shares one description.
Fields without a row get a new one, appended to their table's section; a table
without a section gets a new section at the end of DEFAULT_MD (e.g. objects.md).
"""
import csv
import re
import sys
from pathlib import Path

HEADER = "| Display label | Column | Tooltip | Notes |\n|---|---|---|---|"


def esc(text):
    return text.replace("|", "\\|").strip()


def main(texts_path, tooltips_dir, default_md):
    originals = {p: p.read_bytes().decode("utf-8") for p in Path(tooltips_dir).glob("*.md")}
    newline = {p: "\r\n" if "\r\n" in text else "\n" for p, text in originals.items()}
    files = {p: text.replace("\r\n", "\n").split("\n") for p, text in originals.items()}
    with open(texts_path, encoding="utf-8", newline="") as f:
        texts = list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    replaced = added = 0
    for t in texts:
        table, col, label, text = t["table"], t["column"], t["label"], esc(t["text"])
        done = False
        for path, lines in files.items():
            start = next((i for i, l in enumerate(lines) if l.startswith(f"## Table `{table}`")), None)
            if start is None:
                continue
            end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
            for i in range(start, end):
                line = lines[i]
                if not line.startswith("|") or line.startswith("|---"):
                    continue
                cells = line.strip().strip("|").split("|")
                for j, cell in enumerate(cells):
                    if re.fullmatch(r"\s*`[^`]+`(?:\s*(?:,|/|&|and|or)?\s*`[^`]+`)*\s*", cell) \
                            and f"`{col}`" in cell and j + 1 < len(cells):
                        cells[j + 1] = f" {text} "
                        lines[i] = "|" + "|".join(cells) + "|"
                        done = True
                        replaced += 1
                        break
                if done:
                    break
            if not done:
                last = max(i for i in range(start, end) if lines[i].startswith("|"))
                width = len(lines[last].strip().strip("|").split("|"))
                row = ["", label, f"`{col}`", text, ""] if width == 5 else [label, f"`{col}`", text, ""]
                lines.insert(last + 1, "| " + " | ".join(row) + " |")
                done = True
                added += 1
            break
        if not done:
            path = Path(tooltips_dir) / default_md
            lines = files[path]
            if not any(l.startswith(f"## Table `{table}`") for l in lines):
                lines += ["", "---", "", f"## Table `{table}`", "", HEADER]
            lines.append(f"| {label} | `{col}` | {text} | |")
            added += 1
    for path, lines in files.items():
        text = "\n".join(lines)
        if text != originals[path].replace("\r\n", "\n"):  # only files that really changed
            path.write_bytes(text.replace("\n", newline[path]).encode("utf-8"))
    print(f"{replaced} descriptions replaced, {added} rows added")


if __name__ == "__main__":
    main(*sys.argv[1:4])
