#!/usr/bin/env bash
# Ingest a directory of markdown documents into one softwiki knowledge base,
# throttled by the number of documents still in extraction.
#
# usage: trial_ingest.sh <dir> <api_base> <pg_container> <db_name> [max_inflight]

set -u

DIR=${1:?dir}
API=${2:?api base}
PG=${3:?pg container}
DB=${4:?db name}
MAX=${5:-3}
LOG="$DIR/_ingest.log"
ROLE="wiki-manage"
STALL_SECONDS=${STALL_SECONDS:-480}

touch "$LOG"

release_stalled() {
  sudo docker exec "$PG" psql -U softwiki -d "$DB" -tAc \
    "update documents set status='failed' where status in ('pending','extracting')" >/dev/null 2>&1
  echo "watchdog: marked stalled documents as failed" >> "$LOG"
}

inflight() {
  sudo docker exec "$PG" psql -U softwiki -d "$DB" -tAc \
    "select count(*) from documents where status in ('pending','extracting')" 2>/dev/null | tr -d '[:space:]'
}

total=$(ls -1 "$DIR"/*.md 2>/dev/null | wc -l)
done_n=0
last_change=$(date +%s)
last_n=-1
echo "starting: $total files, max_inflight=$MAX" | tee -a "$LOG"

for f in "$DIR"/*.md; do
  [ -e "$f" ] || continue
  base=$(basename "$f")
  if grep -qF "$base" "$LOG" 2>/dev/null; then
    continue
  fi

  while :; do
    n=$(inflight)
    n=${n:-0}
    if [ "$n" -lt "$MAX" ]; then break; fi
    now=$(date +%s)
    if [ "$n" != "$last_n" ]; then
      last_n=$n
      last_change=$now
    elif [ $((now - last_change)) -gt "$STALL_SECONDS" ]; then
      release_stalled
      last_change=$now
    fi
    sleep 4
  done

  resp=$(curl -s --max-time 120 -H "X-SoftWiki-Role: $ROLE" -F "file=@$f" "$API/api/ingest/file")
  done_n=$((done_n + 1))
  printf '%s\t%s\n' "$base" "$resp" >> "$LOG"
  if [ $((done_n % 10)) -eq 0 ]; then
    echo "queued $done_n/$total (inflight=$n)" | tee -a "$LOG"
  fi
done

echo "upload phase done: $done_n new" | tee -a "$LOG"
last_change=$(date +%s)
last_n=-1
while :; do
  n=$(inflight)
  n=${n:-0}
  if [ "$n" -eq 0 ]; then break; fi
  now=$(date +%s)
  if [ "$n" != "$last_n" ]; then
    last_n=$n
    last_change=$now
  elif [ $((now - last_change)) -gt "$STALL_SECONDS" ]; then
    release_stalled
    last_change=$now
  fi
  echo "waiting: $n still extracting" >> "$LOG"
  sleep 15
done
echo "all extraction finished" | tee -a "$LOG"
