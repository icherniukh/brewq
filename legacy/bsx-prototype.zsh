#!/usr/bin/env zsh
# bsx — brew search with name / 30-day installs / description, sorted by popularity
# Config: BSX_CACHE (default: ~/.cache/brew-all.json), BSX_MAX_AGE (default: 86400)
: "${BSX_CACHE:=${HOME}/.cache/brew-all.json}"
: "${BSX_MAX_AGE:=86400}"
_BSX_LOCK=/tmp/bsx-cache.lock

_bsx-build-cache() {
  brew info --json=v2 --eval-all > "${BSX_CACHE}.tmp" || return 1
  curl -s https://formulae.brew.sh/api/analytics/install/30d.json \
    > "${BSX_CACHE}.f30.tmp" 2>/dev/null || true
  curl -s https://formulae.brew.sh/api/analytics/cask-install/30d.json \
    > "${BSX_CACHE}.c30.tmp" 2>/dev/null || true
  curl -s https://formulae.brew.sh/api/analytics/install/365d.json \
    > "${BSX_CACHE}.f365.tmp" 2>/dev/null || true
  curl -s https://formulae.brew.sh/api/analytics/cask-install/365d.json \
    > "${BSX_CACHE}.c365.tmp" 2>/dev/null || true
  jq -s '
    .[1].items as $f30  |
    .[2].items as $c30  |
    .[3].items as $f365 |
    .[4].items as $c365 |
    .[0].formulae |= map(
      . as $f |
      ($f30[]  | select(.formula == $f.name) | .count) as $i30  |
      ($f365[] | select(.formula == $f.name) | .count) as $i365 |
      .installs_30d  = ($i30  // "-") |
      .installs_365d = ($i365 // "-")
    ) |
    .[0].casks |= map(
      . as $c |
      ($c30[]  | select(.cask == $c.token) | .count) as $n30  |
      ($c365[] | select(.cask == $c.token) | .count) as $n365 |
      .installs_30d  = ($n30  // "-") |
      .installs_365d = ($n365 // "-")
    ) |
    .[0]
  ' "${BSX_CACHE}.tmp" "${BSX_CACHE}.f30.tmp" "${BSX_CACHE}.c30.tmp" \
    "${BSX_CACHE}.f365.tmp" "${BSX_CACHE}.c365.tmp" \
    > "${BSX_CACHE}" 2>/dev/null \
    || mv "${BSX_CACHE}.tmp" "${BSX_CACHE}"
  rm -f "${BSX_CACHE}.tmp" "${BSX_CACHE}.f30.tmp" "${BSX_CACHE}.c30.tmp" \
    "${BSX_CACHE}.f365.tmp" "${BSX_CACHE}.c365.tmp"
}

_bsx-bg-refresh() {
  [[ -f "$_BSX_LOCK" ]] && return
  touch "$_BSX_LOCK"
  ( nice -n 19 _bsx-build-cache; rm -f "$_BSX_LOCK" ) &>/dev/null &
}

_bsx-cache-stale() {
  [[ ! -f "$BSX_CACHE" ]] && return 0
  local age=$(( $(date +%s) - $(stat -f %m "$BSX_CACHE") ))
  (( age >= BSX_MAX_AGE ))
}

_bsx-render() {
  local period="${1:-30d}" show_url="${2:-0}"
  local cols=${COLUMNS:-0}
  (( cols <= 0 )) && cols=$(tput cols 2>/dev/null || echo 100)
  (( cols <= 0 )) && cols=100
  local bold=$'\033[1m' dim=$'\033[2m' reset=$'\033[0m'
  local formula_color=$'\033[38;5;183m'     # lavender (formula)
  local cask_color=$'\033[38;5;115m'        # seafoam green (cask)
  local green=$'\033[32m'
  local deprecated_color=$'\033[38;5;208m'  # true orange (deprecated)
  local disabled_color=$'\033[38;5;167m'    # red (disabled)
  local -a rows=()
  while IFS= read -r line; do rows+=("$line"); done
  local max_name=0 max_inst=0
  for row in "${rows[@]}"; do
    local rname="${row%%	*}"
    (( ${#rname} > max_name )) && max_name=${#rname}
    local rinst="${row#*	}"; rinst="${rinst%%	*}"
    (( ${#rinst} > max_inst )) && max_inst=${#rinst}
  done
  local nw=$(( max_name + 2 ))
  (( nw < 6 )) && nw=6
  (( nw > 34 )) && nw=34
  local iw=$(( max_inst + 1 ))
  (( iw < 6 )) && iw=6
  local dw=$(( cols - nw - iw - 4 ))
  (( dw < 20 )) && dw=20
  local inst_label="(${period})"
  (( iw >= 14 )) && inst_label="INSTALLS (${period})"
  printf "\n${bold}%-${nw}s  %${iw}s  %s${reset}\n" "NAME" "$inst_label" "DESCRIPTION"
  printf '%s\n' "$(printf '─%.0s' $(seq 1 $(( nw + iw + dw + 4 ))))"
  printf '%s\n' "${rows[@]}" | awk -F'\t' -v nw="$nw" -v iw="$iw" -v dw="$dw" \
      -v fc="$formula_color" -v cc="$cask_color" -v green="$green" \
      -v depr="$deprecated_color" -v disb="$disabled_color" \
      -v bold="$bold" -v dim="$dim" -v reset="$reset" \
      -v show_url="$show_url" '
    function wrap(text, width,    i, words, n, cur, out) {
      n = split(text, words, " ")
      cur = ""; out = ""
      for (i = 1; i <= n; i++) {
        if (cur == "") { cur = words[i] }
        else if (length(cur) + 1 + length(words[i]) <= width) { cur = cur " " words[i] }
        else { out = out (out ? "\n" : "") cur; cur = words[i] }
      }
      return out (out ? "\n" : "") cur
    }
    {
      name=$1; inst=$2; desc=$3; type=$4; installed=$5; status=$6; url=$7
      if (length(name) > nw - 2) { name = substr(name, 1, nw - 3) "…"; status = "" }
      color = (type == "cask") ? cc : fc
      status_prefix = ""
      if (status == "disabled")        status_prefix = disb "(disabled) " reset
      else if (status == "deprecated") status_prefix = depr "(deprecated) " reset
      marker = (installed == "1") ? (" " green "✔" reset) : ""
      pad = sprintf("%*s  %*s  ", nw, "", iw, "")
      wrapped = wrap(desc, dw)
      n = split(wrapped, lines, "\n")
      display = (installed == "1") ? (bold color name reset marker) : (color name reset)
      npad = nw - length(name) - (installed == "1" ? 2 : 0); if (npad < 0) npad = 0
      printf "%s%*s  %*s  %s%s\n", display, npad, "", iw, inst, status_prefix, lines[1]
      for (i = 2; i <= n; i++) printf "%s%s\n", pad, lines[i]
      if (show_url == "1" && url != "" && url != "-") printf "%s%s%s%s\n", pad, dim, url, reset
    }
    END { printf "\n" }
  '
}

_bsx-from-cache() {
  local sort=installs mixed=1 period=30d show_url=0
  while [[ "$1" == -* ]]; do
    case "$1" in
      -i) sort=installs ;;
      -n) sort=name ;;
      -m) mixed=0 ;;
      -y) period=365d ;;
      -u) show_url=1 ;;
      -h) echo "Usage: bsx [-i|-n] [-m] [-y] [-u] [-h] <query>
  -i  sort by install count (default)
  -n  sort by name
  -m  group Formulae then Casks (like brew search)
  -y  show 365-day installs instead of 30-day
  -u  show homepage URL below each result
  -h  show this help"; return ;;
    esac
    shift
  done
  local names_json
  names_json=$(brew search "$@" | grep -v '^==>' | grep -v '^$' | jq -Rn '[inputs]')
  [[ "$names_json" == "[]" ]] && echo "No results." && return
  jq -r --argjson names "$names_json" \
        --arg sort "$sort" \
        --argjson mixed "$mixed" \
        --arg period "$period" '
    def installs: if $period == "365d" then (.installs_365d // "-") else (.installs_30d // "-") end;
    def by_installs: sort_by(installs | gsub(","; "") | tonumber? // 0) | reverse;
    def by_name: sort_by(.full_name // .name);
    def sorted: if $sort == "name" then by_name else by_installs end;
    def row: [(.full_name // .name), installs, (.desc // "-"), ._type,
              (if (.installed | length) > 0 then "1" else "0" end),
              (if .disabled then "disabled" elif .deprecated then "deprecated" else "" end),
              (.homepage // "-")] | @tsv;
    [.formulae[] | select(.full_name | IN($names[])) | . + {_type: "formula"}] as $f |
    [.casks[]    | select(.token | IN($names[])) | .name = .token | . + {_type: "cask"}] as $c |
    if $mixed == 1 then ($f + $c | sorted)
    else            ($f | sorted) + ($c | sorted)
    end | .[] | row
  ' "$BSX_CACHE" | _bsx-render "$period" "$show_url"
}

_bsx-fallback() {
  local names
  names=$(brew search "$@" | grep -v '^==>' | grep -v '^$')
  [[ -z "$names" ]] && echo "No results." && return
  echo "$names" | while read -r pkg; do
    info=$(brew info --json=v2 "$pkg" 2>/dev/null)
    local type="formula"
    echo "$info" | jq -e '.casks[0]' &>/dev/null && type="cask"
    printf "%s\t%s\t%s\t%s\n" \
      "$(echo "$info" | jq -r '.formulae[0].name // .casks[0].token // "-"')" \
      "-" \
      "$(echo "$info" | jq -r '.formulae[0].desc // .casks[0].desc // "-"')" \
      "$type"
  done | _bsx-render
}

if [[ "$1" == "update-cache" ]]; then
  _bsx-build-cache && echo "Cache updated: $BSX_CACHE"
  exit
fi

if [[ ! -f "$BSX_CACHE" ]]; then
  echo "⚠️  Cache not built yet — building in background. Showing live results (slower)..." >&2
  _bsx-bg-refresh
  sleep 0.75
  _bsx-fallback "$@"
  exit
fi

_bsx-cache-stale && _bsx-bg-refresh
_bsx-from-cache "$@"
