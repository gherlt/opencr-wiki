# openCR Wiki sources

Source of the pages on https://opencr.com/wiki/ (MediaWiki). The English
pages here are the reference version; the wiki is published from them.

## Layout

- `pages/` — one file per wiki page, in wikitext. The file name is the page
  title with `:` written as `__`, `/` (subpages) as `--` and spaces as `_`
  (`Template__Draft.wiki` → `Template:Draft`,
  `How_openCR_is_structured--Records_and_their_sections.wiki` →
  `How openCR is structured/Records and their sections`).
- `tools/publish.sh` — publishes page files through the bot account.

## Publishing

```bash
tools/publish.sh pages/*.wiki
```

The script reads the bot credentials from
`~/.config/opencr-wiki/bot.env` (`WIKI_API`, `WIKI_BOT_USER`,
`WIKI_BOT_PASS`). That file is not part of the repository.

`MediaWiki:` pages (sidebar, interface messages) need interface rights the
bot does not have. The script skips them; they are published on the server
with MediaWiki's `edit` maintenance script:

```bash
ssh opencr-wiki -p 222 'cd ~/public_html/opencr_com/w && php84 maintenance/run.php edit --user "OpenCR Claude" --bot --summary "Update sidebar" "MediaWiki:Sidebar"' < pages/MediaWiki__Sidebar.wiki
```

## Translations

The guides are translated into Spanish and German with the Translate
extension. A translatable English page carries `<languages/>` at the top and
its text inside `<translate>` tags. Marking it for translation splits the text
into units and numbers them with `<!--T:n-->` markers. The translations appear
as `Page/es` and `Page/de`. `{{Draft}}` and the navigation templates are
translatable as well, and a translated page shows them in its own language.

- `translations/es/`, `translations/de/` — one file per page, named like the
  English file. Each unit starts with a marker line `<!--T:n-->`;
  `<!--T:Page display title-->` holds the translated title. Links point to
  the translated page (`[[Glossary/es|Glosario]]`).
- `tools/translations.py` — marks pages, pulls the marked source back, pushes
  translations and lists missing or outdated units.

```bash
python tools/translations.py mark "Glossary"        # templates: add --transclusion --no-title
python tools/translations.py pull "Glossary"        # the markers belong in pages/ too
python tools/translations.py push es translations/es/Glossary.wiki
python tools/translations.py status
```

When an English page changes: publish it with its markers, mark it again
(changed units become outdated), pull it, update the translations, and push
them. Push with `--clear-fuzzy` to keep an outdated translation that needs no
change. Only Spanish and German are open for translation.

The navigation templates put translated pages into language categories
(`[[Category:Visitor guide{{#translation:}}]]` gives `Category:Visitor guide/es`).
Those category pages are ordinary pages in `pages/`
(`Category__Visitor_guide--es.wiki`); after publishing a new one, set its page
language with `python tools/translations.py setlang es "Category:Visitor guide/es"`.
The wiki allows about 90 edits a minute; `push` waits when it hits the limit.

## Field reference

The pages `Field reference/…` are generated, not written by hand. Their
sources are deliberately **not** in this public repository, because they
name database tables and columns:

- the field descriptions and the page configuration live in the private
  application repository (`docs/tooltips/*.md` and
  `docs/tooltips/wiki-reference.json` in open.cr_reports);
- the live schema and the vocabularies are read from the database with
  read-only queries;
- the field captions come from the English admin forms.

Working files go to `data/`, which is ignored by Git. The steps:

```bash
python tools/extract_form_labels.py C:/xampp/open_ENG data/form_labels.tsv
python tools/build_field_data.py data TOOLTIPS/wiki-reference.json
python tools/vocab_sql.py data/columns.tsv data/fks.tsv TOOLTIPS/wiki-reference.json > data/vocab.sql
python tools/gen_field_reference.py data TOOLTIPS Objects          # one entity page
python tools/gen_field_reference.py data TOOLTIPS "Base tables"    # all vocabularies in use
```

(`TOOLTIPS` = the `docs/tooltips` folder of open.cr_reports. `columns.tsv`,
`fks.tsv`, `vocab.tsv` and the small filter files `qualifier_flags.tsv`,
`system_languages.tsv` and `event_relation_flags.tsv` come from read-only
queries on the database. The filters reproduce what the forms offer: date
fields only date qualifiers, language fields only the system languages,
event roles per kind of participant.)
`tools/apply_field_texts.py` writes new field descriptions into the field
notes. `gen_field_reference.py` lists fields whose description is missing
in `data/review_<page>.tsv`.

## Conventions

- Field and section names are written as they appear in the forms, never as
  database column names.
- Facts are checked against the code, the forms and the field notes in
  `docs/` of the openCR application repository (open.cr_reports); nothing is guessed.
- New pages start with `{{Draft}}` and end with `{{Editor guide}}` (editor
  guide pages).
