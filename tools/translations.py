"""Page translation (Translate extension) through the bot account.

    python tools/translations.py mark TITLE... [--transclusion] [--no-title]
    python tools/translations.py pull TITLE...
    python tools/translations.py push LANG FILE... [--clear-fuzzy]
    python tools/translations.py status [TITLE...]
    python tools/translations.py setlang LANG TITLE...

mark     marks the English source page for translation (priority languages
         Spanish and German, others disallowed). --transclusion lets the page
         be transcluded in the language of the including page (templates);
         --no-title leaves the page title untranslated (templates).
pull     writes the current wikitext of the source pages, including the unit
         markers <!--T:n--> that marking adds, back to pages/. Run it after
         every mark, or the next publish removes the markers.
push     publishes the translations in translations/LANG/FILE: one unit per
         marker line "<!--T:id-->", the text below it up to the next marker
         ("Page display title" is the translated title). Only changed units are
         saved. A unit whose English source changed is "outdated"; once its
         translation is checked, --clear-fuzzy saves it again unchanged.
status   lists, per page and language, the units that are missing or outdated.
setlang  sets the page language of ordinary pages (generated pages, categories).

File names follow pages/ ("__" = ":", "--" = "/", "_" = space). Credentials
come from bot.env (WIKI_API, WIKI_BOT_USER, WIKI_BOT_PASS), by default
~/.config/opencr-wiki/bot.env; the password is never printed.
"""
import http.cookiejar
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LANGS = ["es", "de"]
PRIORITY_REASON = "openCR is published in English, Spanish and German"
FUZZY = "!!FUZZY!!"
MARKER_RE = re.compile(r"^<!--T:([^>]+?)-->[ \t]*$")


def title_to_file(title):
    return title.replace(" ", "_").replace("/", "--").replace(":", "__") + ".wiki"


def file_to_title(path):
    name = Path(path).name
    if name.endswith(".wiki"):
        name = name[:-5]
    return name.replace("__", ":").replace("--", "/").replace("_", " ")


class Wiki:
    def __init__(self):
        env = Path(os.environ.get("WIKI_ENV", Path.home() / ".config/opencr-wiki/bot.env"))
        cfg = {}
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
        self.api = cfg["WIKI_API"]
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.opener.addheaders = [("User-Agent", "opencr-wiki translations.py")]
        token = self.get(action="query", meta="tokens", type="login")["query"]["tokens"]["logintoken"]
        res = self.post(action="login", lgname=cfg["WIKI_BOT_USER"], lgpassword=cfg["WIKI_BOT_PASS"], lgtoken=token)
        if res.get("login", {}).get("result") != "Success":
            sys.exit("Login failed: " + res.get("login", {}).get("result", "?"))
        self.csrf = self.get(action="query", meta="tokens")["query"]["tokens"]["csrftoken"]

    def _call(self, params, post):
        params = dict(params, format="json", formatversion="2")
        data = urllib.parse.urlencode(params).encode("utf-8")
        if post:
            req = urllib.request.Request(self.api, data=data)
        else:
            req = urllib.request.Request(self.api + "?" + data.decode("ascii"))
        with self.opener.open(req, timeout=60) as r:
            res = json.loads(r.read().decode("utf-8"))
        if "error" in res:
            raise RuntimeError(f"{res['error'].get('code')}: {res['error'].get('info')}")
        return res

    def get(self, **params):
        return self._call(params, False)

    def post(self, **params):
        return self._call(params, True)

    def wikitext(self, title):
        res = self.get(action="query", prop="revisions", titles=title, rvprop="content|ids", rvslots="main")
        page = res["query"]["pages"][0]
        if page.get("missing"):
            return None, None
        rev = page["revisions"][0]
        return rev["slots"]["main"]["content"], rev["revid"]

    def units(self, title, lang):
        """Unit key -> {definition, translation, fuzzy} of a translatable page."""
        out, cont = {}, {}
        while True:
            res = self.get(action="query", list="messagecollection", mcgroup="page-" + title,
                           mclanguage=lang, mcprop="definition|translation|tags", mclimit="max", **cont)
            for m in res["query"]["messagecollection"]:
                unit = m["key"].rsplit("/", 1)[-1]
                out[unit] = {"definition": m.get("definition"), "translation": m.get("translation"),
                             "fuzzy": "fuzzy" in m.get("tags", [])}
            if "continue" not in res:
                return out
            cont = res["continue"]

    def edit(self, title, text, summary):
        res = self.post(action="edit", title=title, text=text, summary=summary, bot="1", token=self.csrf)
        return "nochange" in res.get("edit", {})


def read_translation(path):
    units, current, lines = {}, None, []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        m = MARKER_RE.match(line)
        if m:
            if current is not None:
                units[current] = "\n".join(lines).strip()
            current, lines = m.group(1).strip().replace(" ", "_"), []
        elif current is not None:
            lines.append(line)
        elif line.strip():
            sys.exit(f"{path}: text before the first marker")
    if current is not None:
        units[current] = "\n".join(lines).strip()
    return units


def markup_counts(text):
    return {k: text.count(k) for k in ("[[", "]]", "{{", "}}", "'''", "{|", "|}", "\n|-", "\n*", "\n#", "<br />")}


def cmd_mark(wiki, args):
    transclusion = "--transclusion" in args
    translate_title = "no" if "--no-title" in args else "yes"
    for title in [a for a in args if not a.startswith("--")]:
        _, revid = wiki.wikitext(title)
        res = wiki.post(action="markfortranslation", title=title, revid=revid, translatetitle=translate_title,
                        prioritylanguages="|".join(LANGS), forcepriority="1", priorityreason=PRIORITY_REASON,
                        transclusion="yes" if transclusion else "no", token=wiki.csrf)
        print("MARKED", title, json.dumps(res.get("markfortranslation", res), ensure_ascii=False))


def cmd_pull(wiki, args):
    for title in args:
        text, _ = wiki.wikitext(title)
        if text is None:
            print("MISSING", title)
            continue
        path = ROOT / "pages" / title_to_file(title)
        old = path.read_text(encoding="utf-8") if path.exists() else None
        new = text if text.endswith("\n") else text + "\n"
        if old == new:
            print("SAME ", title)
        else:
            path.write_bytes(new.encode("utf-8"))
            print("PULLED", title)


def cmd_push(wiki, args):
    clear_fuzzy = "--clear-fuzzy" in args
    args = [a for a in args if not a.startswith("--")]
    lang, files = args[0], args[1:]
    if lang not in LANGS:
        sys.exit(f"unknown language {lang}")
    for f in files:
        path = Path(f)
        if not path.exists():
            path = ROOT / "translations" / lang / Path(f).name
        title = file_to_title(path)
        local = read_translation(path)
        remote = wiki.units(title, lang)
        unknown = sorted(set(local) - set(remote))
        if unknown:
            sys.exit(f"{title}: units not in the source page: {', '.join(unknown)}")
        missing = sorted(set(remote) - set(local), key=lambda u: (not u.isdigit(), int(u) if u.isdigit() else 0, u))
        saved = same = 0
        for unit, text in local.items():
            if not text:
                continue
            r = remote[unit]
            if unit != "Page_display_title" and markup_counts(text) != markup_counts(r["definition"] or ""):
                print(f"  WARN {title} T:{unit}: markup differs from the English unit")
            current = (r["translation"] or "")
            fuzzy = r["fuzzy"] or current.startswith(FUZZY)
            current = current.replace(FUZZY, "").strip()
            if current == text and not (fuzzy and clear_fuzzy):
                if fuzzy:
                    print(f"  OUTDATED {title} T:{unit} (check it, then push with --clear-fuzzy)")
                same += 1
                continue
            wiki.edit(f"Translations:{title}/{unit}/{lang}", text, f"Translation ({lang}) from opencr-wiki")
            saved += 1
        print(f"PUSHED {title} [{lang}]: {saved} saved, {same} unchanged"
              + (f", untranslated: {', '.join(missing)}" if missing else ""))


def cmd_status(wiki, args):
    titles = args
    if not titles:
        res = wiki.get(action="query", meta="messagegroups", mgprop="id|label", mgfilter="page-*")
        titles = [g["id"][5:] for g in res["query"]["messagegroups"] if g["id"].startswith("page-")]
    for title in titles:
        for lang in LANGS:
            units = wiki.units(title, lang)
            missing = [u for u, v in units.items() if not v["translation"]]
            fuzzy = [u for u, v in units.items() if v["translation"] and v["fuzzy"]]
            state = "complete" if not missing and not fuzzy else f"missing {missing} outdated {fuzzy}"
            print(f"{title} [{lang}] {len(units)} units: {state}")


def cmd_setlang(wiki, args):
    lang, titles = args[0], args[1:]
    for title in titles:
        try:
            wiki.post(action="setpagelanguage", title=title, lang=lang, reason="Page language", token=wiki.csrf)
            print("LANG", lang, title)
        except RuntimeError as e:
            print("FAIL", title, e)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2 or sys.argv[1] not in ("mark", "pull", "push", "status", "setlang"):
        sys.exit(__doc__)
    wiki = Wiki()
    globals()["cmd_" + sys.argv[1]](wiki, sys.argv[2:])


if __name__ == "__main__":
    main()
