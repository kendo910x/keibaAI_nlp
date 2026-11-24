"""Mechanical article-to-entity indexing. Coordinates are Unicode code points."""
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from store import Phase, required, transaction


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unit_id: UUID | None = None
    start_char: int | None = Field(None, ge=0)
    end_char: int | None = Field(None, gt=0)
    quote: str | None = Field(None, min_length=1, max_length=1024)
    target_id: UUID | None = None
    horse_id: UUID | None = None
    horse_label: str | None = None
    race_id: UUID | None = None
    race_label: str | None = None
    phase: Phase | None = None


def select_unit(conn, article_id, body, target, current):
    has_range = target.start_char is not None or target.end_char is not None
    if sum([target.unit_id is not None, has_range, target.quote is not None]) > 1:
        raise ValueError("Supply only one unit selector")
    if target.unit_id is not None:
        row = conn.execute("SELECT unit_id FROM text_units WHERE article_id=%s AND unit_id=%s",
                           (article_id, target.unit_id)).fetchone()
        return required(row, "Unit does not belong to this article")["unit_id"]
    if body is None:
        raise ValueError("An article without source text has no text unit")
    if target.quote is not None:
        start = body.find(target.quote)
        if start < 0:
            raise ValueError("Exact quote absent from source")
        pos = body.find(target.quote, start + 1)
        if pos >= 0:
            candidates = [(start, start + len(target.quote))]
            while pos >= 0 and len(candidates) < 20:
                candidates.append((pos, pos + len(target.quote)))
                pos = body.find(target.quote, pos + 1)
            raise ValueError(f"Ambiguous quote. Choose start_char/end_char from {candidates}"
                             + (" (more matches)" if pos >= 0 else ""))
        end = start + len(target.quote)
    elif has_range:
        start, end = target.start_char, target.end_char
        if start is None or end is None or not 0 <= start < end <= len(body):
            raise ValueError("Invalid zero-based, half-open source range")
    elif current:
        return current["unit_id"]
    else:
        start, end = 0, len(body)
    conn.execute("""INSERT INTO text_units(article_id,start_char,end_char) VALUES (%s,%s,%s)
                    ON CONFLICT (article_id,start_char,end_char) DO NOTHING""", (article_id, start, end))
    return conn.execute("""SELECT unit_id FROM text_units
                           WHERE article_id=%s AND start_char=%s AND end_char=%s""",
                        (article_id, start, end)).fetchone()["unit_id"]


def save_targets(article_id: UUID, targets: list[Target]) -> dict:
    """Atomically attach or correct 1–100 targets. Omit selector for full text or the current target's unit.
    A selector is unit_id, [start_char,end_char), or an exact quote. Ambiguous quotes return candidate ranges.
    Supply target_id to correct known IDs/labels and phase; omitted fields retain their values.
    When both an id and a label are given for one entity, the id wins and the label is ignored.
    """
    if not 1 <= len(targets) <= 100:
        raise ValueError("Supply 1 to 100 targets per call")
    with transaction() as conn:
        article = required(conn.execute("SELECT body FROM articles WHERE article_id=%s FOR UPDATE",
                                        (article_id,)).fetchone(), "Unknown article")
        result = []
        for target in targets:
            current = None
            if target.target_id:
                current = required(conn.execute(
                    """SELECT t.* FROM unit_targets t JOIN text_units u USING (unit_id)
                       WHERE u.article_id=%s AND t.target_id=%s""",
                    (article_id, target.target_id)).fetchone(), "Target does not belong to this article")
            unit = select_unit(conn, article_id, article["body"], target, current)
            if current and current["unit_id"] != unit:
                raise ValueError("A correction must refer to the target's existing unit")
            values = {}
            for entity in ("horse", "race"):
                key, label = entity + "_id", entity + "_label"
                for name in (key, label):
                    values[name] = getattr(target, name) if name in target.model_fields_set else (current or {}).get(name)
                if getattr(target, key) is not None and label not in target.model_fields_set:
                    values[label] = None
                if getattr(target, label) is not None and key not in target.model_fields_set:
                    values[key] = None
                if values[key] is not None and values[label] is not None:
                    values[label] = None
            values.update(unit_id=unit, phase=target.phase, target_id=target.target_id)
            if current:
                sql = """UPDATE unit_targets SET horse_id=%(horse_id)s,horse_label=%(horse_label)s,
                         race_id=%(race_id)s,race_label=%(race_label)s,phase=coalesce(%(phase)s,phase)
                         WHERE target_id=%(target_id)s RETURNING *"""
            else:
                sql = """INSERT INTO unit_targets AS t (unit_id,horse_id,horse_label,race_id,race_label,phase)
                         VALUES (%(unit_id)s,%(horse_id)s,%(horse_label)s,%(race_id)s,%(race_label)s,
                                 coalesce(%(phase)s,'unknown'))
                         ON CONFLICT (unit_id,horse_id,race_id,horse_label,race_label) DO UPDATE
                         SET phase=coalesce(%(phase)s,t.phase) RETURNING *"""
            result.append(conn.execute(sql, values).fetchone())
        return {"targets": result}
