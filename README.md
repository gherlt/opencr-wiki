# openCR Wiki sources

Source of the pages on https://opencr.com/wiki/ (MediaWiki). The English
pages here are the reference version; the wiki is published from them.

## Layout

- `pages/` — one file per wiki page, in wikitext. The file name is the page
  title with `:` written as `__` and spaces as `_`
  (`Template__Draft.wiki` → `Template:Draft`).
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

## Conventions

- Field and section names are written as they appear in the forms, never as
  database column names.
- Facts are checked against the code, the forms and the field notes in
  `docs/` of the openCR application repository (open.cr_reports); nothing is guessed.
- New pages start with `{{Draft}}` and end with `{{Editor guide}}` (editor
  guide pages).
