"""Generates one page of the field reference.

    python tools/gen_field_reference.py DATA_DIR TOOLTIPS_DIR PAGE

DATA_DIR      columns.tsv, fks.tsv, form_labels.tsv, vocab.tsv (never committed)
TOOLTIPS_DIR  docs/tooltips of the (private) application repository: the field
              notes (*.md) and wiki-reference.json, which says which tables make
              up each page and which columns are automatic
PAGE          a page name from wiki-reference.json, e.g. "Objects"

Writes pages/Field_reference--PAGE.wiki and DATA_DIR/review_PAGE.tsv, the list
of fields whose description is missing or still technical. The wiki page shows
only the labels editors see, never table or column names.
"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_field_data import parse_tooltips, read_tsv  # noqa: E402

INLINE_VALUES = 30          # vocabularies up to this size are listed in full
FK_NOTE_RE = re.compile(r"FK\s*→\s*`([A-Za-z_]+)(?:\.[A-Za-z_]+)?`")


def humanize(name):
    name = re.sub(r"_text$", "", name)
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name).replace("_", " ").strip()
    return name[:1].upper() + name[1:]


def vocab_title(table):
    return humanize(table).replace("relationtypes", "relation types").replace("prooftypes", "proof types") \
        .replace("datasource", "data source").replace("transactiontypes", "transaction types") \
        .replace("recordtypes", "record types").replace("sourcetypes", "source types")


def base_of(table):
    t = re.sub(r"_text$", "", table)
    m = re.match(r"^v([A-Z]\w+?)Text$", t)
    if m:
        t = re.sub(r"(?<!^)([A-Z])", r"_\1", m.group(1)).lower()
    return t


def main(data_dir, tooltips_dir, page):
    data, tips_dir = Path(data_dir), Path(tooltips_dir)
    config = json.load(open(tips_dir / "wiki-reference.json", encoding="utf-8"))
    spec = config["pages"][page]
    automatic = {c.lower() for c in config["automatic_columns"]}
    entity = set(config["entity_tables"])
    LINK_KINDS = config["link_kinds"]          # entity tables a field can point to, as editors call them
    aliases = config.get("form_table_aliases", {})

    cols = defaultdict(list)
    for r in read_tsv(data / "columns.tsv"):
        cols[r["TABLE_NAME"]].append(r)
    fks = {(r["TABLE_NAME"], r["COLUMN_NAME"]): r["REFERENCED_TABLE_NAME"] for r in read_tsv(data / "fks.tsv")}
    labels = {}
    for r in read_tsv(data / "form_labels.tsv"):
        labels[(aliases.get(r["table"], r["table"]), r["column"])] = \
            [c for c in r["captions"].split(" | ") if c]
    vocab = defaultdict(list)
    for r in read_tsv(data / "vocab.tsv"):
        vocab[r["vocab"]].append(r["label"].strip())
    tips = parse_tooltips(tips_dir)

    out, review = [], []
    out.append("{{Draft}}")
    out.append(f"Every field of the [[{page}]] forms, in the order of the form. Field names are given as they "
               "appear in the forms; where a field appears under another name in some forms, that name is given "
               "in brackets. Fields filled in automatically (who created or changed an entry, and when) are not listed.")
    out.append("")
    out.append("'''Input:''' ''text'', ''number'', ''tick box'', ''list'' (choose from a fixed list) or a link to "
               "another record. '''Required''' fields must be filled in before saving.")
    for section in spec["sections"]:
        table = section["table"]
        out.append(f"\n== {section['title']} ==")
        if section.get("intro"):
            out.append(section["intro"])
        out.append('{| class="wikitable" style="width:100%"')
        out.append("! style=\"width:18%\" | Field !! Meaning !! style=\"width:14%\" | Input !! style=\"width:28%\" | Values")
        skip = {x.lower() for x in section.get("skip", [])}
        for c in cols.get(table, []):
            name, ctype = c["COLUMN_NAME"], c["COLUMN_TYPE"]
            if "auto_increment" in c["EXTRA"] or name.lower() in automatic or name.lower() in skip:
                continue
            if table != spec["sections"][0]["table"] and name.lower() == spec.get("parent_key", "").lower():
                continue
            caps = labels.get((table, name), [])
            label_tip, tooltip, notes = tips.get(table, {}).get(name, ("", "", ""))
            target = fks.get((table, name))
            if not target:
                m = FK_NOTE_RE.search(notes)
                target = m.group(1) if m else None
            target = base_of(target) if target else None
            if caps:
                label = caps[0]
            elif "/" in label_tip and target in LINK_KINDS:
                # one documentation row for several scope columns: name each one
                label = LINK_KINDS[target].split(" ", 1)[1].capitalize()
            else:
                label = label_tip or humanize(name)
            shown = f"'''{label}'''"
            if len(caps) > 1:
                shown += "<br /><small>(" + "; ".join(caps[1:3]) + ")</small>"
            if not caps:
                shown += "<br /><small>(not in the forms)</small>"

            values = ""
            if target and target in LINK_KINDS:
                kind = f"link to {LINK_KINDS[target]}"
            elif target and target not in entity and target in vocab:
                kind = "list"
                vals = [v for v in vocab[target] if v]
                if len(vals) <= INLINE_VALUES:
                    values = ", ".join(vals)
                else:
                    values = (f"{len(vals)} entries, see [[Field reference/Base tables#{vocab_title(target)}|"
                              f"{vocab_title(target)}]]")
            elif ctype.startswith("tinyint(1)") or (ctype.startswith("tinyint") and tooltip.lower().startswith("tick")):
                kind = "tick box"
            elif re.match(r"(tiny|small|medium|big)?int|decimal|float|double", ctype):
                kind = "number"
            elif re.match(r"(long|medium)?text", ctype):
                kind = "long text"
            elif re.match(r"date|timestamp|datetime", ctype):
                kind = "date"
            else:
                kind = "text"
            required = (c["IS_NULLABLE"] == "NO" and c["COLUMN_DEFAULT"] in ("", "NULL")
                        and kind != "tick box" and c["COLUMN_KEY"] != "PRI")
            if required:
                kind += "<br />'''required'''"

            meaning = tooltip.strip()
            if not meaning or "`" in meaning or "FK" in meaning:
                review.append([table, name, label, meaning or "(missing)"])
                meaning = re.sub(r"`[^`]*`", "", meaning).strip() if meaning else ""
            out.append("|-")
            out.append(f"| {shown} || {meaning} || {kind} || {values}")
        out.append("|}")
    out.append("\n== See also ==")
    out.append(f"* [[{page}]]: how the {page.lower()} forms are used")
    out.append("* [[Field reference]]")
    out.append("\n{{Editor guide}}")

    name = "Field_reference--" + page.replace(" ", "_") + ".wiki"
    Path("pages", name).write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    with open(data / f"review_{page}.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["table", "column", "label", "current_tooltip"])
        w.writerows(review)
    print(f"pages/{name}: {sum(1 for l in out if l == '|-')} fields; {len(review)} to review")


if __name__ == "__main__":
    main(*sys.argv[1:4])
