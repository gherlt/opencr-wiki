"""Generates the pages of the field reference.

    python tools/gen_field_reference.py DATA_DIR TOOLTIPS_DIR PAGE
    python tools/gen_field_reference.py DATA_DIR TOOLTIPS_DIR "Base tables"

DATA_DIR      columns.tsv, fks.tsv, form_labels.tsv, vocab.tsv and the value
              subset files (never committed)
TOOLTIPS_DIR  docs/tooltips of the (private) application repository: the field
              notes (*.md) and wiki-reference.json, which says which tables make
              up each page, which columns are automatic, and how vocabularies
              are titled; a section may fix a field's caption ("labels"), input
              ("kinds") or offered entries ("values") where the form differs
PAGE          a page name from wiki-reference.json, e.g. "Objects"; or
              "Base tables": every vocabulary used by a field of any page

Writes pages/Field_reference--PAGE.wiki and, for entity pages,
DATA_DIR/review_PAGE.tsv, the list of fields whose description is missing or
still technical. The pages show only the labels editors see, never table or
column names.
"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_field_data import parse_tooltips, read_tsv  # noqa: E402

INLINE_VALUES = 30          # vocabularies up to this size are listed in full on entity pages
FK_NOTE_RE = re.compile(r"FK\s*→\s*`([A-Za-z_]+)(?:\.[A-Za-z_]+)?`")
BASE_PAGE = "Field reference/Base tables"


def humanize(name):
    name = re.sub(r"_text$", "", name)
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name).replace("_", " ").strip()
    return name[:1].upper() + name[1:]


def base_of(table):
    t = re.sub(r"_text$", "", table)
    m = re.match(r"^v([A-Z]\w+?)Text$", t)
    if m:
        t = re.sub(r"(?<!^)([A-Z])", r"_\1", m.group(1)).lower()
    return t


class Reference:
    def __init__(self, data_dir, tooltips_dir):
        self.data, tips_dir = Path(data_dir), Path(tooltips_dir)
        self.config = json.load(open(tips_dir / "wiki-reference.json", encoding="utf-8"))
        self.automatic = {c.lower() for c in self.config["automatic_columns"]}
        self.entity = set(self.config["entity_tables"])
        self.link_kinds = self.config["link_kinds"]
        aliases = self.config.get("form_table_aliases", {})
        self.cols = defaultdict(list)
        for r in read_tsv(self.data / "columns.tsv"):
            self.cols[r["TABLE_NAME"]].append(r)
        self.fks = {(r["TABLE_NAME"], r["COLUMN_NAME"]): r["REFERENCED_TABLE_NAME"]
                    for r in read_tsv(self.data / "fks.tsv")}
        self.labels = {}
        for r in read_tsv(self.data / "form_labels.tsv"):
            self.labels[(aliases.get(r["table"], r["table"]), r["column"])] = \
                [c for c in r["captions"].split(" | ") if c]
        self.vocab = defaultdict(list)
        vocab_ids = defaultdict(dict)
        for r in read_tsv(self.data / "vocab.tsv"):
            self.vocab[r["vocab"]].append(r["label"].strip())
            vocab_ids[r["vocab"]][r["id"]] = r["label"].strip()
        # Language lists in the forms offer only the system languages, except
        # where the configuration says a field takes any language.
        self.system_languages = []
        langs = self.data / "system_languages.tsv"
        lang_vocab = self.config.get("language_vocabulary")
        if langs.exists() and lang_vocab:
            self.system_languages = [vocab_ids[lang_vocab].get(r["id"], r["id"]) for r in read_tsv(langs)]
        self.tips = parse_tooltips(tips_dir)
        # Qualifier lists are filtered in the forms: date fields offer only the date
        # qualifiers, number fields only the number qualifiers (flags in the vocabulary).
        self.qualifier_sets = {}
        flags = self.data / "qualifier_flags.tsv"
        if flags.exists():
            rows = read_tsv(flags)
            self.qualifier_sets = {"date": [r["label"].strip() for r in rows if r["ForDates"] == "1"],
                                   "number": [r["label"].strip() for r in rows if r["ForNumbers"] == "1"]}

    def title(self, vocab):
        return self.config.get("vocab_titles", {}).get(vocab, humanize(vocab))

    def fields(self, page):
        """Yields (section, field) for every documented field of a page, in form order."""
        spec = self.config["pages"][page]
        parent = spec.get("parent_key", "")
        for section in spec["sections"]:
            table = section["table"]
            skip = {x.lower() for x in section.get("skip", [])}
            for c in self.cols.get(table, []):
                name, ctype = c["COLUMN_NAME"], c["COLUMN_TYPE"]
                if "auto_increment" in c["EXTRA"] or name.lower() in self.automatic or name.lower() in skip:
                    continue
                if parent and table != spec["sections"][0]["table"] and name.lower() == parent.lower():
                    continue
                yield section, self.field(section, table, c)

    def field(self, section, table, c):
        name, ctype = c["COLUMN_NAME"], c["COLUMN_TYPE"]
        fixed = section.get("labels", {}).get(name)
        caps = [fixed] if fixed else self.labels.get((table, name), [])
        label_tip, tooltip, notes = self.tips.get(table, {}).get(name, ("", "", ""))
        target = self.fks.get((table, name))
        if not target:
            m = FK_NOTE_RE.search(notes)
            target = m.group(1) if m else None
        target = base_of(target) if target else None
        if caps:
            label = caps[0]
        elif "/" in label_tip and target in self.link_kinds:
            # one documentation row for several scope columns: name each one
            label = self.link_kinds[target].split(" ", 1)[1].capitalize()
        else:
            label = label_tip or humanize(name)

        vocab, vals = None, []
        if target and target in self.link_kinds:
            kind = f"link to {self.link_kinds[target]}"
        elif target and target not in self.entity and target in self.vocab:
            kind, vocab = "list", target
            vals = [v for v in self.vocab[target] if v]
            subset = self.config.get("value_subsets", {}).get(f"{table}.{name}")
            if subset and (self.data / subset["file"]).exists():
                vals = [r["label"].strip() for r in read_tsv(self.data / subset["file"]) if r[subset["flag"]] == "1"]
            elif (target == self.config.get("language_vocabulary") and self.system_languages
                  and f"{table}.{name}" not in self.config.get("all_languages_fields", [])):
                vals = self.system_languages
            elif target == self.config.get("qualifier_vocabulary") and self.qualifier_sets:
                vals = self.qualifier_sets["date" if re.search(r"date|born|died", name, re.I) else "number"]
            # where the form's code, not a flag in the data, limits the list
            vals = section.get("values", {}).get(name, vals)
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
        kind = section.get("kinds", {}).get(name, kind)
        required = (c["IS_NULLABLE"] == "NO" and c["COLUMN_DEFAULT"] in ("", "NULL")
                    and kind != "tick box" and c["COLUMN_KEY"] != "PRI")
        return {"table": table, "name": name, "label": label, "caps": caps, "tooltip": tooltip.strip(),
                "kind": kind, "required": required, "vocab": vocab, "values": vals}

    def entity_page(self, page):
        out, review, count, current = [], [], 0, None
        out.append("{{Draft}}")
        out.append(f"Every field of the [[{page}]] forms, in the order of the form. Field names are given as they "
                   "appear in the forms; where a field appears under another name in some forms, that name is given "
                   "in brackets. Fields filled in automatically (who created or changed an entry, and when) are not listed.")
        out.append("")
        out.append("'''Input:''' ''text'', ''number'', ''tick box'', ''list'' (choose from a fixed list) or a link to "
                   "another record. '''Required''' fields must be filled in before saving. Long lists are shown on "
                   f"the [[{BASE_PAGE}|Base tables]] page.")
        for section, f in self.fields(page):
            if section is not current:
                if current is not None:
                    out.append("|}")
                current = section
                out.append(f"\n== {section['title']} ==")
                if section.get("intro"):
                    out.append(section["intro"])
                out.append('{| class="wikitable" style="width:100%"')
                out.append('! style="width:18%" | Field !! Meaning !! style="width:14%" | Input !! '
                           'style="width:28%" | Values')
            shown = f"'''{f['label']}'''"
            if len(f["caps"]) > 1:
                shown += "<br /><small>(" + "; ".join(f["caps"][1:3]) + ")</small>"
            if not f["caps"]:
                shown += "<br /><small>(not in the forms)</small>"
            kind = f["kind"] + ("<br />'''required'''" if f["required"] else "")
            values = ""
            if f["vocab"]:
                if len(f["values"]) <= INLINE_VALUES:
                    values = ", ".join(f["values"])
                else:
                    t = self.title(f["vocab"])
                    values = f"{len(f['values'])} entries, see [[{BASE_PAGE}#{t}|{t}]]"
            meaning = f["tooltip"]
            if not meaning or "`" in meaning or "FK" in meaning:
                review.append([f["table"], f["name"], f["label"], meaning or "(missing)"])
                meaning = re.sub(r"`[^`]*`", "", meaning).strip() if meaning else ""
            out.append("|-")
            out.append(f"| {shown} || {meaning} || {kind} || {values}")
            count += 1
        if current is not None:
            out.append("|}")
        out.append("\n== See also ==")
        out.append(f"* [[{page}]]: how the {page.lower()} forms are used")
        out.append(f"* [[{BASE_PAGE}|Base tables]]: the shared lists behind the dropdowns")
        out.append("* [[Field reference]]")
        out.append("\n{{Editor guide}}")
        self.write(page, out)
        with open(self.data / f"review_{page}.tsv", "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, delimiter="\t", lineterminator="\n")
            w.writerow(["table", "column", "label", "current_tooltip"])
            w.writerows(review)
        print(f"pages/Field_reference--{page.replace(' ', '_')}.wiki: {count} fields; {len(review)} to review")

    def base_tables_page(self):
        usage = defaultdict(list)
        for page in self.config["pages"]:
            for section, f in self.fields(page):
                if f["vocab"]:
                    usage[f["vocab"]].append((page, section["title"], f["label"]))
        out = ["{{Draft}}",
               "Base tables are the shared lists behind the dropdowns of the forms: object types, materials, "
               "qualifiers, countries, languages, types of relations and many more. They are shared by all "
               "catalogues and translated into the interface languages; this page shows the English entries. "
               "Because a change affects every catalogue, new entries are best agreed with the platform "
               "administrator.",
               "",
               "Each list below names the fields that use it. Some fields offer only part of a list; "
               "the field reference of the form shows exactly which entries."]
        out.append("\n== Overview ==")
        for vocab in sorted(usage, key=lambda v: self.title(v).lower()):
            out.append(f"* [[#{self.title(vocab)}|{self.title(vocab)}]] ({len([v for v in self.vocab[vocab] if v])})")
        for vocab in sorted(usage, key=lambda v: self.title(v).lower()):
            t = self.title(vocab)
            entries = [v for v in self.vocab[vocab] if v]
            out.append(f"\n== {t} ==")
            uses = []
            if len(usage[vocab]) <= 6:  # few uses: name each field
                for page, sec, label in usage[vocab]:
                    link = f"[[Field reference/{page}#{sec}|{page} → {sec}]]: ''{label}''"
                    if link not in uses:
                        uses.append(link)
            else:  # many uses: name the sections, grouped by page
                by_page = {}
                for page, sec, _label in usage[vocab]:
                    by_page.setdefault(page, [])
                    if sec not in by_page[page]:
                        by_page[page].append(sec)
                for page, secs in by_page.items():
                    links = ", ".join(f"[[Field reference/{page}#{sec}|{sec}]]" for sec in secs)
                    uses.append(f"'''{page}''' ({links})")
            out.append("'''Used in:''' " + "; ".join(uses) + ".")
            note = self.config.get("vocab_notes", {}).get(vocab)
            if note:
                out.append("")
                out.append(note)
            out.append("")
            out.append(f"{len(entries)} entries:")
            out.append('<div style="column-width:15em; column-gap:2em;">')
            out.extend(f"* {v}" for v in entries)
            out.append("</div>")
        out.append("\n== See also ==")
        out.append("* [[Field reference]]")
        out.append("* [[How openCR is structured]]")
        out.append("\n{{Editor guide}}")
        self.write("Base tables", out)
        print(f"pages/Field_reference--Base_tables.wiki: {len(usage)} vocabularies")

    @staticmethod
    def write(page, out):
        name = "Field_reference--" + page.replace(" ", "_") + ".wiki"
        Path("pages", name).write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")


def main(data_dir, tooltips_dir, page):
    ref = Reference(data_dir, tooltips_dir)
    if page == "Base tables":
        ref.base_tables_page()
    else:
        ref.entity_page(page)


if __name__ == "__main__":
    main(*sys.argv[1:4])
