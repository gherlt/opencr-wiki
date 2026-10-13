"""Prints one read-only SELECT that lists every vocabulary entry with its English label.

    python tools/vocab_sql.py data/columns.tsv data/fks.tsv CONFIG.json | ssh … > data/vocab.tsv

A vocabulary is a table that is referenced by a foreign key or has a "<name>_text"
translation table, and is not listed as an entity table in the configuration.
The English label is the "eng" translation when it is filled, otherwise the base
table's own name column (the usual fallback rule).
"""
import csv
import json
import sys
from collections import defaultdict

TEXT_TYPES = ("varchar", "char", "text", "tinytext", "mediumtext")


def read_tsv(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def main(columns_path, fks_path, config_path):
    config = json.load(open(config_path, encoding="utf-8"))
    entity = set(config["entity_tables"])
    cols = defaultdict(list)
    for r in read_tsv(columns_path):
        cols[r["TABLE_NAME"]].append(r)
    referenced = {r["REFERENCED_TABLE_NAME"] for r in read_tsv(fks_path)}
    bases = {t for t in cols if not t.endswith("_text")}
    vocab = sorted(t for t in bases if t not in entity and (t in referenced or f"{t}_text" in cols))

    def pk(t):
        return next((c["COLUMN_NAME"] for c in cols[t] if c["COLUMN_KEY"] == "PRI"), None)

    def label_col(t, skip):
        for c in cols[t]:
            name = c["COLUMN_NAME"]
            if name.lower() in skip or c["COLUMN_KEY"] == "PRI" and t.endswith("_text") is False:
                continue
            if c["COLUMN_TYPE"].split("(")[0] in TEXT_TYPES and name.lower() not in ("languageid", "id_type"):
                return name
        return None

    parts = []
    for t in vocab:
        key = pk(t)
        if not key:
            continue
        base_label = label_col(t, {key.lower()})
        text = f"{t}_text" if f"{t}_text" in cols else None
        text_key = text_lang = text_label = None
        if text:
            names = {c["COLUMN_NAME"].lower(): c["COLUMN_NAME"] for c in cols[text]}
            text_key = names.get(key.lower())
            text_lang = names.get("languageid")
            text_label = label_col(text, {key.lower(), "languageid", "id"})
        label_expr = f"CONVERT(b.`{base_label}` USING utf8mb4)" if base_label else "NULL"
        join = ""
        if text and text_key and text_lang and text_label:
            label_expr = f"COALESCE(NULLIF(CONVERT(x.`{text_label}` USING utf8mb4), ''), {label_expr})"
            join = (f" LEFT JOIN `{text}` x ON x.`{text_key}` = b.`{key}` AND x.`{text_lang}` = 'eng'")
        parts.append(f"SELECT CONVERT('{t}' USING utf8mb4) AS vocab, CONVERT(b.`{key}` USING utf8mb4) AS id, "
                     f"{label_expr} AS label FROM `{t}` b{join}")
    print("\nUNION ALL\n".join(parts))


if __name__ == "__main__":
    main(*sys.argv[1:4])
