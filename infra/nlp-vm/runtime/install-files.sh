#!/usr/bin/env bash
# Stage a reviewed checkout or git archive on VM15. Service activation is a separate operator action.
set -euo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
release=${1:-$(git -C "$root" rev-parse HEAD)}
[[ "$release" =~ ^[a-f0-9]{40}$ ]]
base=/srv/nlp/runtime
snapshot=/srv/nlp/backups/runtime-files-$(date -u +%Y%m%dT%H%M%SZ)
install -d -m 0700 "$snapshot"
install -d -m 0755 "$base/app" "$base/work"
install -d -m 0700 -o 10000 -g 10000 "$base/data"
# Preserve live improvements from Hermes before updating the reviewed skills.
for name in keiba-search keiba-coordinate keiba-interpret; do
    if [[ -d /srv/nlp/hermes/skills/$name ]]; then
        cp -a "/srv/nlp/hermes/skills/$name" "$snapshot/"
    fi
done
if [[ -d /srv/nlp/trial/hermes/skills ]]; then
    install -d -m 0700 "$snapshot/trial-skills"
    for dir in /srv/nlp/trial/hermes/skills/keiba-*; do
        [[ ! -d "$dir" ]] || cp -a "$dir" "$snapshot/trial-skills/"
    done
fi
cp -p /srv/nlp/hermes-runtime/config.yaml "$snapshot/"
for unit in nlp-dashboard.container nlp-hermes.container; do
    if [[ -f /etc/containers/systemd/$unit ]]; then cp -p "/etc/containers/systemd/$unit" "$snapshot/"; fi
done
infra="$root/infra/nlp-vm"
install -m 0644 "$root"/poc/search_research/*.py "$infra"/runtime/*.py "$infra"/hermes/store.py "$infra"/runtime/dashboard.css "$base/app/"
install -m 0644 "$infra/runtime/"*.prompt.txt "$base/work/"
install -m 0644 "$root/AGENTS.md" "$base/work/PROJECT.md"
install -m 0644 "$infra/hermes/AGENTS.md" "$base/work/AGENTS.md"
for home in /srv/nlp/hermes /srv/nlp/trial/hermes; do
    [[ -d "$home" ]] || continue
for name in keiba-search keiba-coordinate keiba-interpret; do
    dest="$home/skills/$name"
    install -d -o 10000 -g 10000 -m 0755 "$dest" "$dest/references"
    install -o 10000 -g 10000 -m 0644 "$root/skills/$name/SKILL.md" "$dest/"
    if [[ -d "$root/skills/$name/references" ]]; then
        install -o 10000 -g 10000 -m 0644 "$root/skills/$name"/references/*.md "$dest/references/"
    fi
    install -o 10000 -g 10000 -m 0644 "$root/AGENTS.md" "$dest/references/work-rules.md"
done
done
install -m 0644 "$infra/hermes/config.yaml" /srv/nlp/hermes-runtime/config.yaml
install -m 0644 "$infra/quadlet/nlp-hermes.container" "$infra/quadlet/nlp-dashboard.container" /etc/containers/systemd/
if [[ -f /srv/nlp/trial/database ]]; then
    sed -e 's/ContainerName=nlp-hermes$/ContainerName=nlp-hermes-trial/' \
        -e 's@/srv/nlp/hermes:/opt/data@/srv/nlp/trial/hermes:/opt/data@' \
        -e 's@/srv/nlp/hermes-private/nlp_app:/run/secrets/nlp_app@/srv/nlp/trial/private/nlp_trial_app:/run/secrets/nlp_trial_app@' \
        -e 's@/srv/nlp/runtime/data:@/srv/nlp/trial/data:@' \
        -e 's@/srv/nlp/runtime/database:@/srv/nlp/trial/database:@' \
        -e '/Volume=.*database:ro/a Volume=/srv/nlp/trial/request.json:/run/keiba/trial.json:ro' \
        -e '/^WantedBy=/d' "$infra/quadlet/nlp-hermes.container" > /etc/containers/systemd/nlp-hermes-trial.container
    sed -e 's/ContainerName=nlp-dashboard$/ContainerName=nlp-dashboard-trial/' \
        -e 's@/srv/nlp/runtime/database:@/srv/nlp/trial/database:@' \
        -e 's@/srv/nlp/hermes/cron:@/srv/nlp/trial/hermes/cron:@' \
        -e 's@/srv/nlp/hermes-private/nlp_viewer:/run/secrets/nlp_viewer@/srv/nlp/trial/private/nlp_trial_viewer:/run/secrets/nlp_trial_viewer@' \
        "$infra/quadlet/nlp-dashboard.container" > /etc/containers/systemd/nlp-dashboard-trial.container
fi
install -m 0644 "$infra"/systemd/* /etc/systemd/system/
printf '%s\n' "$release" > "$base/RELEASE"
systemctl daemon-reload
printf 'Staged %s. Previous files in %s\n' "$release" "$snapshot"
