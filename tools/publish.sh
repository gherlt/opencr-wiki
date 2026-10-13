#!/bin/bash
# Publishes pages/*.wiki files to the openCR Wiki through the bot account.
#
#   tools/publish.sh pages/Main_Page.wiki [more files…]
#
# The page title comes from the file name: "__" becomes ":" and "_" becomes
# a space (Template__Draft.wiki -> "Template:Draft").
# Credentials are read from bot.env (WIKI_API, WIKI_BOT_USER, WIKI_BOT_PASS),
# by default ~/.config/opencr-wiki/bot.env; the password is never printed.
# MediaWiki: pages need interface-admin rights the bot does not have; they
# are skipped here and published on the server instead (see README.md).
set -euo pipefail

ENVF="${WIKI_ENV:-$HOME/.config/opencr-wiki/bot.env}"
SUMMARY="${SUMMARY:-Update from opencr-wiki}"
[ -f "$ENVF" ] || { echo "bot.env not found: $ENVF" >&2; exit 1; }
while IFS='=' read -r k v || [ -n "$k" ]; do
	v="${v%$'\r'}"
	case "$k" in
		WIKI_API) API="$v" ;;
		WIKI_BOT_USER) BOT_USER="$v" ;;
		WIKI_BOT_PASS) BOT_PASS="$v" ;;
	esac
done < "$ENVF"

JAR=$(mktemp)
trap 'rm -f "$JAR" "$JAR.title"' EXIT
api() { curl -sS -c "$JAR" -b "$JAR" "$@"; }

# Tokens are read from XML: JSON escapes the "+\" suffix of MediaWiki tokens.
LOGIN_TOKEN=$(api "$API?action=query&meta=tokens&type=login&format=xml" | grep -oE 'logintoken="[^"]+"' | cut -d'"' -f2)
RESULT=$(api --data-urlencode "lgname=$BOT_USER" --data-urlencode "lgpassword=$BOT_PASS" \
	--data-urlencode "lgtoken=$LOGIN_TOKEN" "$API?action=login&format=json" | grep -oE '"result":"[^"]*"' | cut -d'"' -f4)
[ "$RESULT" = "Success" ] || { echo "Login failed: $RESULT" >&2; exit 1; }
CSRF=$(api "$API?action=query&meta=tokens&format=xml" | grep -oE 'csrftoken="[^"]+"' | cut -d'"' -f2)

for f in "$@"; do
	name=$(basename "$f" .wiki)
	title="${name//__/:}"
	title="${title//_/ }"
	if [[ "$title" == MediaWiki:* ]]; then
		echo "SKIP  $title (interface page, publish on the server)"
		continue
	fi
	# The title goes through a file: Windows curl re-encodes non-ASCII arguments.
	printf '%s' "$title" > "$JAR.title"
	title_file="$JAR.title"
	command -v cygpath >/dev/null && title_file=$(cygpath -m "$title_file")
	out=$(api --data-urlencode "title@$title_file" --data-urlencode "text@$f" \
		--data-urlencode "summary=$SUMMARY" --data-urlencode "token=$CSRF" \
		-d bot=1 "$API?action=edit&format=json")
	status=$(printf '%s' "$out" | grep -oE '"result":"[^"]*"' | cut -d'"' -f4 || true)
	if [ "$status" = "Success" ]; then
		if printf '%s' "$out" | grep -q '"nochange"'; then echo "SAME  $title"; else echo "OK    $title"; fi
	else
		echo "FAIL  $title: $(printf '%s' "$out" | grep -oE '"(code|info)":"[^"]*"' | tr '\n' ' ')"
	fi
done
