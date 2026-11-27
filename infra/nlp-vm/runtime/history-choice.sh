#!/bin/sh
set -eu
pidfile=/var/lib/keiba/history-choice.pid
if [ "${1:-}" = stop ]; then
    if [ -r "$pidfile" ]; then
        pid=$(cat "$pidfile")
        case "$pid" in *[!0-9]*|'') exit 1;; esac
        if [ -r "/proc/$pid/cmdline" ] && tr '\0' ' ' <"/proc/$pid/cmdline" | grep -Fq '/opt/nlp-research/history-choice.sh'; then
            /bin/kill -TERM -- "-$pid"
        fi
    fi
    exit 0
fi
echo "$$" >"$pidfile"
trap 'rm -f "$pidfile"' EXIT
cd /opt/nlp-research
flock /var/lib/keiba/local-model.lock hermes chat --oneshot -Q --toolsets skills,mcp-collection -s keiba-search -s keiba-coordinate --max-turns 14 --query-file /opt/nlp-research/history.prompt.txt
