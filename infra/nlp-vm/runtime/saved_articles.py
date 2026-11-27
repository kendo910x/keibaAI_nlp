"""Freeze the saved versions from the two completed trial collections. Never starts a worker."""

import argparse
import fcntl
import json
import os
import uuid
from pathlib import Path

import research
from corpus import connect
from jobs import create
from profile_db import trial


def fixed_targets(c, sources, accepted, configuration):
    kinds = c.execute(
        "SELECT id,kind,state FROM plans WHERE id=ANY(%s)", (sources,)
    ).fetchall()
    if {p["kind"] for p in kinds} != {"history", "daily"} or any(
        p["state"] not in ("done", "partial") for p in kinds
    ):
        raise ValueError("Supply the two finished collection plans")
    history = next(str(p["id"]) for p in kinds if p["kind"] == "history")
    caps = list(accepted)
    rows = c.execute(
        """WITH reached AS (
               SELECT DISTINCT cap.version_id,cap.id,cap.observed_at,
                      nullif(cap.evidence->>'published_label','') IS NOT NULL dated,h.plan_id::text source
               FROM plan_hits h JOIN captures cap ON cap.id=h.capture_id
               WHERE h.plan_id=ANY(%s) AND cap.version_id IS NOT NULL
           ), origins AS (
               SELECT version_id,array_agg(DISTINCT source ORDER BY source) origins FROM reached GROUP BY version_id
           ), chosen AS (
               SELECT DISTINCT ON (version_id) version_id,id,observed_at FROM reached
               ORDER BY version_id,(id=ANY(%s)) DESC,dated DESC,observed_at,id
           )
           SELECT version_id,id,origins FROM chosen JOIN origins USING(version_id)
           ORDER BY (id=ANY(%s)) DESC,
             row_number() OVER (PARTITION BY (%s=ANY(origins)) ORDER BY observed_at,id),observed_at,id""",
        (sources, caps, caps, history),
    ).fetchall()
    targets = [
        dict(
            type="interpret",
            version=r["version_id"],
            capture=r["id"],
            origins=r["origins"],
            reuse_id=accepted.get(r["id"]),
        )
        for r in rows
    ]
    if {t["capture"] for t in targets if t["reuse_id"]} != set(caps):
        raise ValueError(
            "An accepted capture is outside the collection or duplicates a version"
        )
    skill, settings = research.interpretation_config()
    for t in targets:
        if t["reuse_id"] is None:
            continue
        article = research.read("captures", t["capture"])
        _, _, key = research.interpretation_input(article, skill, settings)
        saved = research.read("interpretations", t["reuse_id"])
        row = c.execute(
            """SELECT id FROM interpretations WHERE id=%s AND capture_id=%s AND version_id=%s
                 AND input_key=%s AND skill_hash=%s AND status='ok'""",
            (
                t["reuse_id"],
                t["capture"],
                t["version"],
                key,
                configuration["skill_sha256"],
            ),
        ).fetchone()
        if (
            not row
            or saved.get("input_key") != key
            or saved["status"] != "ok"
            or saved["id"] != t["reuse_id"]
            or saved["capture_id"] != t["capture"]
        ):
            raise ValueError(
                "Accepted result no longer matches its stored input: " + t["capture"]
            )
    return targets


def target_digest(targets):
    return research.digest(json.dumps(targets, sort_keys=True, separators=(",", ":")))


def prepare(path, sources, accepted_path, count, reuse_count):
    if not trial():
        raise ValueError("This plan belongs to the mounted trial database")
    sources = sorted(set(sources))
    if len(sources) != 2:
        raise ValueError("Supply one history plan and one daily plan")
    accepted = json.loads(accepted_path.read_text())
    if len(accepted) != reuse_count or len(set(accepted.values())) != reuse_count:
        raise ValueError("Unexpected accepted result inventory")
    skill, settings = research.interpretation_config()
    configuration = dict(
        skill_sha256=research.digest(skill), settings=settings, endpoint=research.LLM
    )
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists():
            manifest = json.loads(path.read_bytes())
        else:
            with connect() as c:
                targets = fixed_targets(c, sources, accepted, configuration)
            if len(targets) != count:
                raise ValueError(f"Found {len(targets)} versions, expected {count}")
            manifest = dict(
                sources=[str(s) for s in sources],
                configuration=configuration,
                frozen_at=research.now(),
                targets=targets,
                sha256=target_digest(targets),
            )
            stage = path.with_suffix(".tmp")
            stage.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            stage.replace(path)
        targets = manifest["targets"]
        if (
            manifest["sources"] != [str(s) for s in sources]
            or manifest["configuration"] != configuration
            or len({t["version"] for t in targets}) != len(targets)
            or len(targets) != count
            or {t["capture"]: t["reuse_id"] for t in targets if t["reuse_id"]}
            != accepted
            or manifest["sha256"] != target_digest(targets)
        ):
            raise ValueError(
                "Frozen manifest differs from the requested inventory or configuration"
            )
        definition = {k: v for k, v in manifest.items() if k != "targets"}
        definition.update(manifest=str(path), count=count, accepted=reuse_count)
        ident = str(
            uuid.uuid5(uuid.NAMESPACE_URL, "keiba/saved-versions/" + manifest["sha256"])
        )
        create(
            "interpret",
            "保存済み検証記事の馬別解釈",
            "saved_versions",
            targets,
            definition,
            ident=ident,
        )
        with connect() as c:
            plan = c.execute("SELECT input FROM plans WHERE id=%s", (ident,)).fetchone()
            stored = [
                r["target"]
                for r in c.execute(
                    "SELECT target FROM work_items WHERE plan_id=%s ORDER BY position",
                    (ident,),
                )
            ]
            if plan["input"] != definition or stored != targets:
                raise ValueError("Existing plan and immutable manifest disagree")
    return ident


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("accepted", type=Path)
    parser.add_argument("sources", nargs=2, type=uuid.UUID)
    parser.add_argument("--versions", required=True, type=int)
    parser.add_argument("--reuse", required=True, type=int)
    args = parser.parse_args()
    os.umask(0o077)
    print(
        prepare(args.manifest, args.sources, args.accepted, args.versions, args.reuse)
    )
