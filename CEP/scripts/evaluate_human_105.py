#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import statistics
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

FACETS = {
    "F1": "Architecture / built environment",
    "F2": "Arts / creative expression",
    "F3": "Contemporary / living culture",
    "F4": "Craft / making practices",
    "F5": "Cultural landscape / human-place relations",
    "F6": "Foodways / culinary culture",
    "F7": "Historical / cultural-past content",
    "F8": "Religious / spiritual cultural content",
    "F9": "Social / community practices",
}
FACET_CODES = tuple(FACETS)
ASSERTION_STATES = ("S1", "S2", "S4", "S5", "S6")
VALID_COMPONENT_TYPES = {
    "activity_practice", "place_poi_stop", "activity_at_place", "c0_te_whole"
}
VALID_COMPONENT_ROLES = {
    "fixed", "optional", "alternative", "contextual", "meeting_point", "cross_promotion"
}
EXPECTED_N = 105
EXPECTED_SAMPLE_SHA = "90dfeddd777af58b0ae493b12d1fbac3b5ff15b04ebcec1fc066f7e701713964"

NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

# -----------------------------
# XLSX read-only parser
# -----------------------------
def _col_name(n: int) -> str:
    s = ""
    while n:
        n, rem = divmod(n - 1, 26)
        s = chr(65 + rem) + s
    return s

def load_xlsx(path: Path) -> dict[str, dict[str, Any]]:
    """Read cell values/formulas from an .xlsx using only Python stdlib."""
    z = zipfile.ZipFile(path)
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall("a:si", NS):
            texts = []
            for t in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"):
                texts.append(t.text or "")
            shared.append("".join(texts))

    wbroot = ET.fromstring(z.read("xl/workbook.xml"))
    relroot = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rid_to_target = {r.attrib["Id"]: r.attrib["Target"] for r in relroot}

    sheets: dict[str, dict[str, Any]] = {}
    for sh in wbroot.find("a:sheets", NS):
        name = sh.attrib["name"]
        rid = sh.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        target = rid_to_target[rid]
        p = target.lstrip("/") if target.startswith("/") else (
            target if target.startswith("xl/") else "xl/" + target
        )
        p = str(Path(p))
        root = ET.fromstring(z.read(p))
        cells: dict[str, Any] = {}
        formulas: dict[str, str] = {}
        for c in root.findall(".//a:c", NS):
            ref = c.attrib["r"]
            typ = c.attrib.get("t")
            f = c.find("a:f", NS)
            v = c.find("a:v", NS)
            isel = c.find("a:is", NS)
            val: Any = None
            if typ == "s" and v is not None:
                val = shared[int(v.text)]
            elif typ == "inlineStr" and isel is not None:
                val = "".join(
                    t.text or ""
                    for t in isel.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
                )
            elif typ == "str" and v is not None:
                val = v.text
            elif typ == "b" and v is not None:
                val = (v.text == "1")
            elif v is not None:
                txt = v.text
                try:
                    if txt is None:
                        val = None
                    elif re.fullmatch(r"-?\d+", txt):
                        val = int(txt)
                    else:
                        val = float(txt)
                except Exception:
                    val = txt
            cells[ref] = val
            if f is not None:
                formulas[ref] = f.text or ""
        sheets[name] = {"cells": cells, "formulas": formulas}
    return sheets

def sheet_rows(
    book: dict[str, dict[str, Any]],
    sheet_name: str,
    ncols: int,
    nrows: int,
) -> list[dict[str, Any]]:
    if sheet_name not in book:
        raise ValueError(f"Missing worksheet: {sheet_name}")
    cells = book[sheet_name]["cells"]
    matrix = []
    for r in range(1, nrows + 1):
        matrix.append([
            cells.get(f"{_col_name(c)}{r}")
            for c in range(1, ncols + 1)
        ])
    headers = matrix[0]
    return [dict(zip(headers, row)) for row in matrix[1:]]

def notblank(v: Any) -> bool:
    return v is not None and str(v).strip() != ""

def to_float(v: Any) -> float:
    return float(v)

def to_int(v: Any) -> int:
    return int(float(v))

# -----------------------------
# Metrics
# -----------------------------
def prf(tp: float, fp: float, fn: float) -> dict[str, float]:
    """Precision/recall/F1 with explicit zero-F1 when an observed class has no TP.

    Precision or recall remains NaN only when its denominator is undefined.
    F1 is NaN only when there are no positive events on either side (tp=fp=fn=0);
    otherwise a complete miss correctly receives F1=0.
    """
    p = tp / (tp + fp) if tp + fp else float("nan")
    r = tp / (tp + fn) if tp + fn else float("nan")
    if tp + fp + fn == 0:
        f = float("nan")
    else:
        pp = 0.0 if p != p else p
        rr = 0.0 if r != r else r
        f = 2 * pp * rr / (pp + rr) if pp + rr else 0.0
    return {"precision": p, "recall": r, "f1": f}

def qwk(y_true: list[int], y_pred: list[int], weights: list[float] | None = None) -> float:
    if not y_true:
        return float("nan")
    weights = weights or [1.0] * len(y_true)
    levels = [1, 2, 3]
    idx = {x: i for i, x in enumerate(levels)}
    obs = [[0.0] * 3 for _ in range(3)]
    ht = [0.0] * 3
    hp = [0.0] * 3
    total = 0.0
    for a, b, w in zip(y_true, y_pred, weights):
        obs[idx[a]][idx[b]] += w
        ht[idx[a]] += w
        hp[idx[b]] += w
        total += w
    num = den = 0.0
    for i in range(3):
        for j in range(3):
            ww = ((i - j) ** 2) / 4.0
            expected = ht[i] * hp[j] / total
            num += ww * obs[i][j]
            den += ww * expected
    return 1.0 - num / den if den else float("nan")

def multiclass_metrics(
    pairs: list[tuple[str, str, float]],
    labels: Iterable[str],
) -> dict[str, Any]:
    labels = list(labels)
    confusion = {a: {b: 0.0 for b in labels} for a in labels}
    for true, pred, w in pairs:
        confusion[true][pred] += w
    total = sum(sum(x.values()) for x in confusion.values())
    accuracy = sum(confusion[x][x] for x in labels) / total if total else float("nan")
    per = {}
    observed_f1 = []
    all_label_f1 = []
    for lab in labels:
        tp = confusion[lab][lab]
        fp = sum(confusion[t][lab] for t in labels if t != lab)
        fn = sum(confusion[lab][p] for p in labels if p != lab)
        support = sum(confusion[lab].values())
        predicted_support = sum(confusion[t][lab] for t in labels)
        per[lab] = prf(tp, fp, fn)
        per[lab].update({"support": support, "predicted_support": predicted_support})
        f1 = per[lab]["f1"]
        if support + predicted_support > 0:
            observed_f1.append(0.0 if f1 != f1 else f1)
        all_label_f1.append(0.0 if f1 != f1 else f1)
    macro_observed = sum(observed_f1) / len(observed_f1) if observed_f1 else float("nan")
    macro_all = sum(all_label_f1) / len(all_label_f1) if all_label_f1 else float("nan")
    return {
        "accuracy": accuracy,
        "macro_f1": macro_observed,
        "macro_f1_observed_states": macro_observed,
        "macro_f1_all_frozen_states": macro_all,
        "confusion": confusion,
        "per_class": per,
    }

# -----------------------------
# Data extraction / validation
# -----------------------------
def load_inputs(human_path: Path, model_path: Path) -> dict[str, Any]:
    h = load_xlsx(human_path)
    m = load_xlsx(model_path)

    human_te = sheet_rows(h, "BLIND_TE_GOLD", 7, 106)
    human_components_all = sheet_rows(h, "GOLD_COMPONENTS_BLIND", 9, 2101)
    human_assertions_all = sheet_rows(h, "GOLD_ASSERTIONS_BLIND", 12, 3151)
    human_salience_all = sheet_rows(h, "TE_FACET_SALIENCE_BLIND", 5, 946)
    human_metadata = sheet_rows(h, "HUMAN_METADATA", 2, 11)

    model_te = sheet_rows(m, "TE_Predictions", 7, 106)
    model_components = sheet_rows(m, "Component_Predictions", 13, 372)
    model_assertions = sheet_rows(m, "Assertion_Predictions", 19, 256)
    model_facets = sheet_rows(m, "Facet_Predictions", 12, 130)
    model_abst = sheet_rows(m, "Abstention_Predictions", 5, 22)
    selection = sheet_rows(m, "Selection_Audit", 16, 106)

    human_components = [r for r in human_components_all if notblank(r["HUMAN_component_label"])]
    human_assertions = [
        r for r in human_assertions_all
        if any(notblank(r[k]) for k in (
            "HUMAN_gold_component_id", "HUMAN_facet_code", "HUMAN_assertion_state"
        ))
    ]
    human_salience = [
        r for r in human_salience_all
        if notblank(r["HUMAN_salience_if_S1_fixed_supported"])
    ]

    return {
        "human_te": human_te,
        "human_components": human_components,
        "human_assertions": human_assertions,
        "human_salience_all": human_salience_all,
        "human_salience": human_salience,
        "human_metadata": human_metadata,
        "model_te": model_te,
        "model_components": model_components,
        "model_assertions": model_assertions,
        "model_facets": model_facets,
        "model_abstentions": model_abst,
        "selection": selection,
    }

def validate(data: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    hte = data["human_te"]
    hcomp = data["human_components"]
    hass = data["human_assertions"]
    hsalall = data["human_salience_all"]
    mte = data["model_te"]
    mcomp = data["model_components"]
    mass = data["model_assertions"]
    mfac = data["model_facets"]
    sel = data["selection"]

    def issue(severity: str, code: str, eval_id: str = "", item_id: str = "", detail: str = ""):
        issues.append({
            "severity": severity, "code": code, "eval_id": eval_id,
            "item_id": item_id, "detail": detail
        })

    if len(hte) != EXPECTED_N:
        issue("BLOCKER", "human_te_count", detail=f"Expected {EXPECTED_N}, got {len(hte)}")
    if len(mte) != EXPECTED_N:
        issue("BLOCKER", "model_te_count", detail=f"Expected {EXPECTED_N}, got {len(mte)}")

    h_ids = [r["eval_id"] for r in hte]
    m_ids = [r["eval_id"] for r in mte]
    if len(set(h_ids)) != EXPECTED_N:
        issue("BLOCKER", "human_eval_id_uniqueness")
    if set(h_ids) != set(m_ids):
        issue("BLOCKER", "human_model_eval_id_mismatch")

    hte_by = {r["eval_id"]: r for r in hte}
    mte_by = {r["eval_id"]: r for r in mte}

    for eid in sorted(set(h_ids) & set(m_ids)):
        if hte_by[eid]["title"] != mte_by[eid]["title"]:
            issue("BLOCKER", "title_mismatch", eid)
        if hte_by[eid]["description"] != mte_by[eid]["description"]:
            issue("BLOCKER", "description_mismatch", eid)
        if hte_by[eid]["HUMAN_complete"] != "YES":
            issue("BLOCKER", "human_te_not_complete", eid)
        if hte_by[eid]["HUMAN_should_abstain"] not in {"YES", "NO", "UNCERTAIN"}:
            issue("BLOCKER", "invalid_human_abstention", eid)

    comp_by_id = {r["gold_component_id"]: r for r in hcomp}
    if len(comp_by_id) != len(hcomp):
        issue("BLOCKER", "duplicate_gold_component_id")

    for r in hcomp:
        cid = r["gold_component_id"]
        eid = r["eval_id"]
        required = [
            "HUMAN_component_label", "HUMAN_component_type", "HUMAN_component_role",
            "HUMAN_evidence_source_field", "HUMAN_exact_evidence_quote"
        ]
        for k in required:
            if not notblank(r[k]):
                issue("BLOCKER", "missing_component_field", eid, cid, k)
        if r["HUMAN_component_type"] not in VALID_COMPONENT_TYPES:
            issue("BLOCKER", "invalid_component_type", eid, cid, str(r["HUMAN_component_type"]))
        if r["HUMAN_component_role"] not in VALID_COMPONENT_ROLES:
            issue("BLOCKER", "invalid_component_role", eid, cid, str(r["HUMAN_component_role"]))

    for r in hass:
        aid = r["gold_assertion_id"]
        eid = r["eval_id"]
        required = [
            "HUMAN_gold_component_id", "HUMAN_facet_code", "HUMAN_assertion_state",
            "HUMAN_observable_cue", "HUMAN_evidence_source_field", "HUMAN_exact_evidence_quote"
        ]
        for k in required:
            if not notblank(r[k]):
                issue("BLOCKER", "missing_assertion_field", eid, aid, k)
        if r["HUMAN_gold_component_id"] not in comp_by_id:
            issue("BLOCKER", "assertion_bad_component_ref", eid, aid, str(r["HUMAN_gold_component_id"]))
        st = r["HUMAN_assertion_state"]
        fc = r["HUMAN_facet_code"]
        if st not in ASSERTION_STATES:
            issue("BLOCKER", "invalid_assertion_state", eid, aid, str(st))
        if not (fc in FACETS or (st == "S5" and fc == "NONE")):
            issue("BLOCKER", "invalid_assertion_facet", eid, aid, f"{st}/{fc}")
        if st == "S5":
            comp = comp_by_id.get(r["HUMAN_gold_component_id"])
            if comp and comp["HUMAN_component_role"] != "fixed":
                issue("BLOCKER", "s5_on_noneligible_component", eid, aid)

    # Exact human evidence localization.
    for kind, rows, id_key, source_key, quote_key in [
        ("component", hcomp, "gold_component_id", "HUMAN_evidence_source_field", "HUMAN_exact_evidence_quote"),
        ("assertion", hass, "gold_assertion_id", "HUMAN_evidence_source_field", "HUMAN_exact_evidence_quote"),
    ]:
        for r in rows:
            eid = r["eval_id"]
            source = r[source_key]
            quote = r[quote_key]
            if source not in {"title", "description"}:
                issue("BLOCKER", "invalid_evidence_source", eid, r[id_key], str(source))
                continue
            text = hte_by[eid][source]
            count = text.count(quote) if quote else 0
            if count == 0:
                issue("BLOCKER", "human_evidence_zero_match", eid, r[id_key], str(quote))
            elif count > 1:
                issue("BLOCKER", "human_evidence_ambiguous_duplicate", eid, r[id_key],
                      f"occurrences={count}; quote={quote!r}")

    # Derived support/abstention/salience consistency.
    role_by_comp = {r["gold_component_id"]: r["HUMAN_component_role"] for r in hcomp}
    human_supported = defaultdict(set)
    for r in hass:
        if (
            r["HUMAN_assertion_state"] == "S1"
            and role_by_comp.get(r["HUMAN_gold_component_id"]) == "fixed"
            and r["HUMAN_facet_code"] in FACETS
        ):
            human_supported[r["eval_id"]].add(r["HUMAN_facet_code"])

    sal_by = defaultdict(dict)
    for r in hsalall:
        if notblank(r["HUMAN_salience_if_S1_fixed_supported"]):
            val = to_int(r["HUMAN_salience_if_S1_fixed_supported"])
            if val not in {1, 2, 3}:
                issue("BLOCKER", "invalid_salience", r["eval_id"], r["facet_code"], str(val))
            sal_by[r["eval_id"]][r["facet_code"]] = val

    for eid in h_ids:
        derived_abst = "YES" if not human_supported[eid] else "NO"
        actual = hte_by[eid]["HUMAN_should_abstain"]
        if actual != derived_abst:
            issue("BLOCKER", "abstention_logic_mismatch", eid,
                  detail=f"human={actual}, derived={derived_abst}")
        if set(sal_by[eid]) != set(human_supported[eid]):
            issue("BLOCKER", "salience_supported_facet_mismatch", eid,
                  detail=f"supported={sorted(human_supported[eid])}; salience={sorted(sal_by[eid])}")

    # Model sample/selection weights.
    sel_by = {r["eval_id"]: r for r in sel}
    if set(sel_by) != set(h_ids):
        issue("BLOCKER", "selection_eval_id_mismatch")
    total_weight = sum(float(r["sampling_weight"]) for r in sel)
    if abs(total_weight - 643.0) > 1e-8:
        issue("BLOCKER", "sampling_weight_sum", detail=f"Expected 643, got {total_weight}")

    # Review completeness summary.
    review_summary = {}
    for name, rows in [
        ("component", mcomp), ("assertion", mass),
        ("facet", mfac), ("abstention", data["model_abstentions"])
    ]:
        review_cols = [k for k in rows[0] if str(k).startswith("REVIEW_")]
        any_filled = sum(any(notblank(r.get(k)) for k in review_cols) for r in rows)
        complete = sum(r.get("REVIEW_complete") == "YES" for r in rows if "REVIEW_complete" in r)
        review_summary[name] = {
            "rows": len(rows), "rows_with_any_review": any_filled,
            "rows_complete": complete
        }

    return issues, {
        "hte_by": hte_by,
        "comp_by_id": comp_by_id,
        "role_by_comp": role_by_comp,
        "human_supported": human_supported,
        "sal_by": sal_by,
        "selection_by": sel_by,
        "review_summary": review_summary,
    }

# -----------------------------
# Deterministic evaluation
# -----------------------------
def evaluate_deterministic(data: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    hte = data["human_te"]
    hcomp = data["human_components"]
    hass = data["human_assertions"]
    mte = data["model_te"]
    mcomp = data["model_components"]
    mass = data["model_assertions"]
    mfac = data["model_facets"]

    hte_by = ctx["hte_by"]
    role_by_comp = ctx["role_by_comp"]
    human_supported = ctx["human_supported"]
    sal_by = ctx["sal_by"]
    sel_by = ctx["selection_by"]
    weights = {eid: float(r["sampling_weight"]) for eid, r in sel_by.items()}

    model_abst = {
        r["eval_id"]: ("YES" if bool(r["model_cultural_abstention"]) else "NO")
        for r in mte
    }
    model_facets = defaultdict(set)
    model_sal = defaultdict(dict)
    for r in mfac:
        model_facets[r["eval_id"]].add(r["model_facet_code"])
        model_sal[r["eval_id"]][r["model_facet_code"]] = to_int(r["model_salience_ordinal"])

    # Model native eligible components and S1 support.
    model_comp_eligible = {}
    model_eligible_count = Counter()
    for r in mcomp:
        eligible = bool(r["model_cep_eligible"])
        model_comp_eligible[r["model_component_id"]] = eligible
        if eligible:
            model_eligible_count[r["eval_id"]] += 1

    model_s1_comps = defaultdict(lambda: defaultdict(set))
    for r in mass:
        if (
            r["model_assertion_state"] == "S1"
            and model_comp_eligible.get(r["model_component_id"], False)
            and r["model_facet_code"] in FACETS
        ):
            model_s1_comps[r["eval_id"]][r["model_facet_code"]].add(r["model_component_id"])

    # Human native eligible inventory.
    human_fixed_count = Counter()
    for r in hcomp:
        if r["HUMAN_component_role"] == "fixed":
            human_fixed_count[r["eval_id"]] += 1

    human_s1_comps = defaultdict(lambda: defaultdict(set))
    for r in hass:
        if (
            r["HUMAN_assertion_state"] == "S1"
            and role_by_comp.get(r["HUMAN_gold_component_id"]) == "fixed"
            and r["HUMAN_facet_code"] in FACETS
        ):
            human_s1_comps[r["eval_id"]][r["HUMAN_facet_code"]].add(r["HUMAN_gold_component_id"])

    # Abstention.
    abst_rows = []
    for r in hte:
        eid = r["eval_id"]
        abst_rows.append({
            "eval_id": eid,
            "human_abstain": r["HUMAN_should_abstain"],
            "model_abstain": model_abst[eid],
            "sampling_weight": weights[eid],
        })

    def binary_conf(rows, weighted: bool):
        c = Counter()
        for r in rows:
            w = r["sampling_weight"] if weighted else 1.0
            c[(r["human_abstain"], r["model_abstain"])] += w
        tp = c[("YES", "YES")]
        tn = c[("NO", "NO")]
        fp = c[("NO", "YES")]
        fn = c[("YES", "NO")]
        total = tp + tn + fp + fn
        metrics = {
            "tp": tp, "tn": tn, "fp": fp, "fn": fn,
            "accuracy": (tp + tn) / total if total else float("nan"),
            "abstention_precision": tp / (tp + fp) if tp + fp else float("nan"),
            "abstention_recall": tp / (tp + fn) if tp + fn else float("nan"),
        }
        p = metrics["abstention_precision"]; rr = metrics["abstention_recall"]
        metrics["abstention_f1"] = 2*p*rr/(p+rr) if p == p and rr == rr and p+rr else float("nan")
        return metrics

    abstention = {
        "unweighted": binary_conf(abst_rows, False),
        "weighted": binary_conf(abst_rows, True),
        "rows": abst_rows,
    }

    # TE-level facet metrics.
    def facet_eval(weighted: bool):
        per = {fc: {"tp": 0.0, "fp": 0.0, "fn": 0.0, "tn": 0.0} for fc in FACETS}
        tp = fp = fn = 0.0
        exact_num = total_w = 0.0
        rows = []
        for r in hte:
            eid = r["eval_id"]
            w = weights[eid] if weighted else 1.0
            hset = set(human_supported[eid])
            pset = set(model_facets[eid])
            tp += w * len(hset & pset)
            fp += w * len(pset - hset)
            fn += w * len(hset - pset)
            exact_num += w * (hset == pset)
            total_w += w
            rows.append({
                "eval_id": eid,
                "human_facets": ";".join(sorted(hset)),
                "model_facets": ";".join(sorted(pset)),
                "tp": len(hset & pset), "fp": len(pset - hset), "fn": len(hset - pset),
                "exact_set_match": int(hset == pset),
                "sampling_weight": weights[eid],
            })
            for fc in FACETS:
                if fc in hset and fc in pset:
                    per[fc]["tp"] += w
                elif fc not in hset and fc in pset:
                    per[fc]["fp"] += w
                elif fc in hset and fc not in pset:
                    per[fc]["fn"] += w
                else:
                    per[fc]["tn"] += w
        overall = prf(tp, fp, fn)
        overall.update({"tp": tp, "fp": fp, "fn": fn, "exact_set_agreement": exact_num / total_w})
        per_rows = []
        macro = []
        for fc in FACETS:
            met = prf(per[fc]["tp"], per[fc]["fp"], per[fc]["fn"])
            if met["f1"] == met["f1"]:
                macro.append(met["f1"])
            per_rows.append({
                "facet_code": fc, "facet": FACETS[fc],
                **per[fc], **met,
            })
        overall["macro_f1"] = sum(macro) / len(macro) if macro else float("nan")
        return overall, per_rows, rows

    facet_u, per_facet_u, facet_rows = facet_eval(False)
    facet_w, per_facet_w, _ = facet_eval(True)

    # Salience on common supported facets only.
    salience_pairs = []
    for r in hte:
        eid = r["eval_id"]
        common = set(human_supported[eid]) & set(model_facets[eid])
        for fc in sorted(common):
            salience_pairs.append({
                "eval_id": eid, "facet_code": fc, "facet": FACETS[fc],
                "human_salience": int(sal_by[eid][fc]),
                "model_salience": int(model_sal[eid][fc]),
                "abs_error": abs(int(sal_by[eid][fc]) - int(model_sal[eid][fc])),
                "sampling_weight": weights[eid],
            })

    def sal_metrics(weighted: bool):
        if not salience_pairs:
            return {}
        ws = [r["sampling_weight"] if weighted else 1.0 for r in salience_pairs]
        sw = sum(ws)
        y = [r["human_salience"] for r in salience_pairs]
        p = [r["model_salience"] for r in salience_pairs]
        return {
            "n_pairs": len(salience_pairs),
            "weighted_pair_mass": sw,
            "qwk": qwk(y, p, ws),
            "mae": sum(w * abs(a - b) for a, b, w in zip(y, p, ws)) / sw,
            "exact_agreement": sum(w * (a == b) for a, b, w in zip(y, p, ws)) / sw,
            "within_one_agreement": sum(w * (abs(a - b) <= 1) for a, b, w in zip(y, p, ws)) / sw,
        }

    sal_u = sal_metrics(False)
    sal_w = sal_metrics(True)

    # Salience confusion.
    sal_conf_u = Counter()
    sal_conf_w = Counter()
    for r in salience_pairs:
        key = (r["human_salience"], r["model_salience"])
        sal_conf_u[key] += 1
        sal_conf_w[key] += r["sampling_weight"]

    # Primary native Coverage on union of S1-positive human/model facets.
    coverage_rows = []
    for r in hte:
        eid = r["eval_id"]
        union = set(human_supported[eid]) | set(model_facets[eid])
        hden = human_fixed_count[eid]
        mden = model_eligible_count[eid]
        for fc in sorted(union):
            hnum = len(human_s1_comps[eid].get(fc, set()))
            mnum = len(model_s1_comps[eid].get(fc, set()))
            hcov = hnum / hden if hden else None
            mcov = mnum / mden if mden else None
            coverage_rows.append({
                "eval_id": eid, "facet_code": fc, "facet": FACETS[fc],
                "human_numerator": hnum, "human_denominator": hden, "human_coverage": hcov,
                "model_numerator": mnum, "model_denominator": mden, "model_coverage": mcov,
                "coverage_abs_error": abs(hcov - mcov) if hcov is not None and mcov is not None else None,
                "numerator_abs_error": abs(hnum - mnum),
                "denominator_abs_error": abs(hden - mden),
                "exact_numerator": int(hnum == mnum),
                "exact_denominator": int(hden == mden),
                "exact_coverage": int(hcov is not None and mcov is not None and abs(hcov - mcov) < 1e-12),
                "sampling_weight": weights[eid],
            })

    def coverage_metrics(weighted: bool):
        valid = [r for r in coverage_rows if r["coverage_abs_error"] is not None]
        if not valid:
            return {}
        ws = [r["sampling_weight"] if weighted else 1.0 for r in valid]
        sw = sum(ws)
        return {
            "n_union_te_facet_pairs": len(coverage_rows),
            "n_evaluable_pairs": len(valid),
            "coverage_mae": sum(w*r["coverage_abs_error"] for r,w in zip(valid,ws))/sw,
            "numerator_mae": sum(w*r["numerator_abs_error"] for r,w in zip(valid,ws))/sw,
            "denominator_component_count_mae": sum(w*r["denominator_abs_error"] for r,w in zip(valid,ws))/sw,
            "exact_numerator_agreement": sum(w*r["exact_numerator"] for r,w in zip(valid,ws))/sw,
            "exact_denominator_agreement": sum(w*r["exact_denominator"] for r,w in zip(valid,ws))/sw,
            "exact_coverage_agreement": sum(w*r["exact_coverage"] for r,w in zip(valid,ws))/sw,
        }

    cov_u = coverage_metrics(False)
    cov_w = coverage_metrics(True)

    # Native eligible component-count diagnostic.
    comp_count_rows = []
    for r in hte:
        eid = r["eval_id"]
        hc = human_fixed_count[eid]
        mc = model_eligible_count[eid]
        comp_count_rows.append({
            "eval_id": eid, "human_eligible_component_count": hc,
            "model_eligible_component_count": mc,
            "signed_difference_model_minus_human": mc-hc,
            "absolute_difference": abs(mc-hc),
            "sampling_weight": weights[eid],
        })

    def comp_count_metrics(weighted: bool):
        ws = [r["sampling_weight"] if weighted else 1.0 for r in comp_count_rows]
        sw = sum(ws)
        return {
            "mae": sum(w*r["absolute_difference"] for r,w in zip(comp_count_rows,ws))/sw,
            "exact_count_agreement": sum(w*(r["absolute_difference"]==0) for r,w in zip(comp_count_rows,ws))/sw,
        }

    return {
        "abstention": abstention,
        "te_facet": {
            "unweighted": facet_u, "weighted": facet_w,
            "per_facet_unweighted": per_facet_u,
            "per_facet_weighted": per_facet_w,
            "rows": facet_rows,
        },
        "salience": {
            "unweighted": sal_u, "weighted": sal_w,
            "pairs": salience_pairs,
            "confusion_unweighted": sal_conf_u,
            "confusion_weighted": sal_conf_w,
        },
        "coverage": {
            "unweighted": cov_u, "weighted": cov_w,
            "rows": coverage_rows,
        },
        "component_count": {
            "unweighted": comp_count_metrics(False),
            "weighted": comp_count_metrics(True),
            "rows": comp_count_rows,
        },
        "human_summary": {
            "gold_components": len(hcomp),
            "gold_assertions": len(hass),
            "human_abstentions": sum(r["HUMAN_should_abstain"]=="YES" for r in hte),
            "assertion_states": dict(Counter(r["HUMAN_assertion_state"] for r in hass)),
            "supported_salience_pairs": len(data["human_salience"]),
        }
    }

# -----------------------------
# Full matching-dependent evaluation
# -----------------------------
def evaluate_full(data: dict[str, Any], ctx: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    hcomp = data["human_components"]
    hass = data["human_assertions"]
    mcomp = data["model_components"]
    mass = data["model_assertions"]
    sel_by = ctx["selection_by"]
    weights = {eid: float(r["sampling_weight"]) for eid, r in sel_by.items()}

    def issue(code, eid="", item="", detail=""):
        issues.append({"severity":"PENDING","code":code,"eval_id":eid,"item_id":item,"detail":detail})

    # Minimal fields required for final matching-dependent metrics.
    for r in mcomp:
        if not notblank(r["REVIEW_component_match"]):
            issue("component_review_missing", r["eval_id"], r["model_component_id"])
        if r["REVIEW_component_match"] == "MATCH" and not notblank(r["REVIEW_matched_gold_component_id"]):
            issue("component_match_id_missing", r["eval_id"], r["model_component_id"])
    for r in mass:
        if not notblank(r["REVIEW_semantic_grounding"]):
            issue("assertion_grounding_missing", r["eval_id"], r["model_assertion_id"])
        # Assertion matching can legitimately be absent only when explicitly represented as NONE/NOT_MATCH.
        if not notblank(r["REVIEW_matched_gold_assertion_id"]):
            issue("assertion_match_id_missing", r["eval_id"], r["model_assertion_id"])

    if issues:
        return None, issues

    gold_comp_by = {r["gold_component_id"]: r for r in hcomp}
    gold_ass_by = {r["gold_assertion_id"]: r for r in hass}
    human_s1 = defaultdict(lambda: defaultdict(set))
    model_s1 = defaultdict(lambda: defaultdict(set))

    for r in hass:
        if r["HUMAN_assertion_state"]=="S1" and r["HUMAN_facet_code"] in FACETS:
            human_s1[r["eval_id"]][r["HUMAN_gold_component_id"]].add(r["HUMAN_facet_code"])
    for r in mass:
        if r["model_assertion_state"]=="S1" and r["model_facet_code"] in FACETS:
            model_s1[r["eval_id"]][r["model_component_id"]].add(r["model_facet_code"])

    # Component matches; uncertain remains unmatched.
    pred_to_gold = {}
    used_gold = defaultdict(set)
    component_match_rows = []
    for r in mcomp:
        eid = r["eval_id"]
        status = str(r["REVIEW_component_match"]).strip()
        gid = str(r["REVIEW_matched_gold_component_id"]).strip() if notblank(r["REVIEW_matched_gold_component_id"]) else ""
        if status == "MATCH":
            if gid not in gold_comp_by:
                issues.append({"severity":"BLOCKER","code":"invalid_matched_gold_component_id","eval_id":eid,"item_id":r["model_component_id"],"detail":gid})
                continue
            if gold_comp_by[gid]["eval_id"] != eid:
                issues.append({"severity":"BLOCKER","code":"cross_te_component_match","eval_id":eid,"item_id":r["model_component_id"],"detail":gid})
                continue
            if gid in used_gold[eid]:
                issues.append({"severity":"BLOCKER","code":"non_one_to_one_component_match","eval_id":eid,"item_id":r["model_component_id"],"detail":gid})
                continue
            pred_to_gold[r["model_component_id"]] = gid
            used_gold[eid].add(gid)
        elif status not in {"NOT_MATCH","UNCERTAIN"}:
            issues.append({"severity":"BLOCKER","code":"invalid_component_match_status","eval_id":eid,"item_id":r["model_component_id"],"detail":status})
        component_match_rows.append({
            "eval_id": eid, "model_component_id": r["model_component_id"],
            "model_eligible": int(bool(r["model_cep_eligible"])),
            "review_status": status, "matched_gold_component_id": gid or "",
        })

    if any(x["severity"]=="BLOCKER" for x in issues):
        return None, issues

    # Component extraction: eligible/fixed primary + all-component secondary.
    def component_scope_metrics(scope: str):
        tp=fp=fn=0.0
        per_te=[]
        for eid in {r["eval_id"] for r in mcomp}:
            w=weights[eid]
            preds=[r for r in mcomp if r["eval_id"]==eid and (scope=="all" or bool(r["model_cep_eligible"]))]
            golds=[r for r in hcomp if r["eval_id"]==eid and (scope=="all" or r["HUMAN_component_role"]=="fixed")]
            gset={r["gold_component_id"] for r in golds}
            matched=0
            for p in preds:
                gid=pred_to_gold.get(p["model_component_id"])
                if gid in gset:
                    matched+=1
            t=matched
            fpp=len(preds)-matched
            fnn=len(golds)-matched
            tp+=w*t; fp+=w*fpp; fn+=w*fnn
            per_te.append({"eval_id":eid,"tp":t,"fp":fpp,"fn":fnn,"sampling_weight":w})
        met=prf(tp,fp,fn); met.update({"tp":tp,"fp":fp,"fn":fn})
        return met, per_te

    comp_eligible, comp_rows = component_scope_metrics("eligible")
    comp_all, _ = component_scope_metrics("all")

    # Primary component-level S1 facet metric.
    per_facet = {fc: {"tp":0.0,"fp":0.0,"fn":0.0} for fc in FACETS}
    cond_per_facet = {fc: {"tp":0.0,"fp":0.0,"fn":0.0} for fc in FACETS}
    for eid in {r["eval_id"] for r in mcomp}:
        w=weights[eid]
        pred_eligible=[r for r in mcomp if r["eval_id"]==eid and bool(r["model_cep_eligible"])]
        gold_eligible=[r for r in hcomp if r["eval_id"]==eid and r["HUMAN_component_role"]=="fixed"]
        gold_ids={r["gold_component_id"] for r in gold_eligible}
        matched_gold=set()
        matched_pred=set()
        for p in pred_eligible:
            pid=p["model_component_id"]
            gid=pred_to_gold.get(pid)
            if gid in gold_ids:
                matched_pred.add(pid); matched_gold.add(gid)
                hset=human_s1[eid].get(gid,set())
                pset=model_s1[eid].get(pid,set())
                for fc in FACETS:
                    if fc in hset and fc in pset:
                        per_facet[fc]["tp"]+=w; cond_per_facet[fc]["tp"]+=w
                    elif fc not in hset and fc in pset:
                        per_facet[fc]["fp"]+=w; cond_per_facet[fc]["fp"]+=w
                    elif fc in hset and fc not in pset:
                        per_facet[fc]["fn"]+=w; cond_per_facet[fc]["fn"]+=w
        for p in pred_eligible:
            if p["model_component_id"] not in matched_pred:
                for fc in model_s1[eid].get(p["model_component_id"],set()):
                    per_facet[fc]["fp"]+=w
        for g in gold_eligible:
            if g["gold_component_id"] not in matched_gold:
                for fc in human_s1[eid].get(g["gold_component_id"],set()):
                    per_facet[fc]["fn"]+=w

    def summarize_facet_counts(counts):
        rows=[]; ttp=tfp=tfn=0.0; macro=[]
        for fc in FACETS:
            d=counts[fc]; met=prf(d["tp"],d["fp"],d["fn"])
            rows.append({"facet_code":fc,"facet":FACETS[fc],**d,**met})
            ttp+=d["tp"]; tfp+=d["fp"]; tfn+=d["fn"]
            if met["f1"]==met["f1"]: macro.append(met["f1"])
        overall=prf(ttp,tfp,tfn); overall.update({"tp":ttp,"fp":tfp,"fn":tfn,"macro_f1":sum(macro)/len(macro) if macro else float("nan")})
        return overall, rows

    component_s1_primary, component_s1_rows = summarize_facet_counts(per_facet)
    component_s1_cond, component_s1_cond_rows = summarize_facet_counts(cond_per_facet)

    # Assertion matching/state/grounding.
    assertion_pairs=[]
    used_gold_ass=defaultdict(set)
    grounding_counts=Counter()
    grounding_weighted=Counter()
    assertion_match_rows=[]
    for r in mass:
        eid=r["eval_id"]
        raw=str(r["REVIEW_matched_gold_assertion_id"]).strip()
        grounding=str(r["REVIEW_semantic_grounding"]).strip()
        grounding_counts[grounding]+=1
        grounding_weighted[grounding]+=weights[eid]
        gid="" if raw in {"","NONE","NOT_MATCH"} else raw
        matched=False
        if gid:
            if gid not in gold_ass_by:
                issues.append({"severity":"BLOCKER","code":"invalid_matched_gold_assertion_id","eval_id":eid,"item_id":r["model_assertion_id"],"detail":gid})
            elif gold_ass_by[gid]["eval_id"] != eid:
                issues.append({"severity":"BLOCKER","code":"cross_te_assertion_match","eval_id":eid,"item_id":r["model_assertion_id"],"detail":gid})
            elif gid in used_gold_ass[eid]:
                issues.append({"severity":"BLOCKER","code":"non_one_to_one_assertion_match","eval_id":eid,"item_id":r["model_assertion_id"],"detail":gid})
            else:
                used_gold_ass[eid].add(gid); matched=True
                gold_state=gold_ass_by[gid]["HUMAN_assertion_state"]
                assertion_pairs.append((gold_state, r["model_assertion_state"], weights[eid]))
        assertion_match_rows.append({
            "eval_id":eid,"model_assertion_id":r["model_assertion_id"],
            "matched_gold_assertion_id":gid,"matched":int(matched),
            "model_state":r["model_assertion_state"],
            "semantic_grounding":grounding,
            "sampling_weight":weights[eid],
        })

    if any(x["severity"]=="BLOCKER" for x in issues):
        return None, issues

    state_weighted=multiclass_metrics(assertion_pairs,ASSERTION_STATES)
    state_unweighted=multiclass_metrics([(a,b,1.0) for a,b,w in assertion_pairs],ASSERTION_STATES)

    total_gw=sum(grounding_weighted.values())
    semantic_grounding={
        "unweighted": {k: grounding_counts[k]/sum(grounding_counts.values()) for k in GROUNDING_LABELS if sum(grounding_counts.values())},
        "weighted": {k: grounding_weighted[k]/total_gw for k in GROUNDING_LABELS if total_gw},
        "counts": dict(grounding_counts),
        "weighted_counts": dict(grounding_weighted),
    }

    return {
        "component_extraction_primary_eligible_weighted": comp_eligible,
        "component_extraction_secondary_all_weighted": comp_all,
        "component_rows": component_match_rows,
        "component_s1_facet_primary_weighted": component_s1_primary,
        "component_s1_facet_primary_per_facet": component_s1_rows,
        "component_s1_facet_conditional_weighted": component_s1_cond,
        "component_s1_facet_conditional_per_facet": component_s1_cond_rows,
        "assertion_state_unweighted": state_unweighted,
        "assertion_state_weighted": state_weighted,
        "assertion_match_rows": assertion_match_rows,
        "semantic_grounding": semantic_grounding,
    }, issues

GROUNDING_LABELS = ("SUPPORTED","UNSUPPORTED","UNCERTAIN")

# -----------------------------
# Output helpers
# -----------------------------
def safe(v):
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v

def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as f:
        w=csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if fields:
            w.writeheader()
            for r in rows:
                w.writerow({k:safe(r.get(k)) for k in fields})

def jsonable(obj):
    if isinstance(obj, dict):
        return {str(k):jsonable(v) for k,v in obj.items()}
    if isinstance(obj, (list,tuple)):
        return [jsonable(x) for x in obj]
    if isinstance(obj, Counter):
        return {str(k):jsonable(v) for k,v in obj.items()}
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj

def add_metric(rows, family, metric, unweighted=None, weighted=None, denominator=""):
    rows.append({
        "family":family,"metric":metric,
        "unweighted":safe(unweighted),"weighted":safe(weighted),
        "denominator_or_note":denominator
    })

def build_metric_rows(det, full):
    rows=[]
    for k in ["accuracy","abstention_precision","abstention_recall","abstention_f1"]:
        add_metric(rows,"Abstention",k,det["abstention"]["unweighted"][k],det["abstention"]["weighted"][k],"105 outcome-stratified accepted outputs; weighted estimates target 643 accepted outputs")
    for k in ["precision","recall","f1","macro_f1","exact_set_agreement"]:
        add_metric(rows,"TE-level facets",k,det["te_facet"]["unweighted"][k],det["te_facet"]["weighted"][k],"105 TEs; multi-label S1/fixed supported facets")
    for k in ["qwk","mae","exact_agreement","within_one_agreement"]:
        add_metric(rows,"Salience",k,det["salience"]["unweighted"].get(k),det["salience"]["weighted"].get(k),f"{det['salience']['unweighted'].get('n_pairs',0)} common supported TE-facet pairs")
    for k in ["coverage_mae","numerator_mae","denominator_component_count_mae","exact_numerator_agreement","exact_denominator_agreement","exact_coverage_agreement"]:
        add_metric(rows,"Coverage",k,det["coverage"]["unweighted"].get(k),det["coverage"]["weighted"].get(k),f"{det['coverage']['unweighted'].get('n_evaluable_pairs',0)} union S1-positive TE-facet pairs")
    for k in ["mae","exact_count_agreement"]:
        add_metric(rows,"Eligible component-count diagnostic",k,det["component_count"]["unweighted"][k],det["component_count"]["weighted"][k],"105 TEs; native inventories, not component extraction accuracy")
    if full:
        c=full["component_extraction_primary_eligible_weighted"]
        for k in ["precision","recall","f1"]:
            add_metric(rows,"Component extraction (eligible/fixed primary)",k,None,c[k],"Requires human component matching; TE-weighted")
        cf=full["component_s1_facet_primary_weighted"]
        for k in ["precision","recall","f1","macro_f1"]:
            add_metric(rows,"Component-level S1 facet (primary)",k,None,cf[k],"Includes unmatched predicted S1 FP and unmatched human S1 FN")
        st=full["assertion_state_weighted"]
        add_metric(rows,"Assertion state","accuracy",full["assertion_state_unweighted"]["accuracy"],st["accuracy"],"Matched assertions only")
        add_metric(rows,"Assertion state","macro_f1",full["assertion_state_unweighted"]["macro_f1"],st["macro_f1"],"Matched assertions only")
    return rows

def make_charts(outdir: Path, det: dict[str, Any], full: dict[str,Any] | None):
    import matplotlib.pyplot as plt
    outdir.mkdir(parents=True, exist_ok=True)

    # 1 Abstention confusion unweighted
    a=det["abstention"]["unweighted"]
    labels=["Human NO / Model NO","Human NO / Model YES","Human YES / Model NO","Human YES / Model YES"]
    vals=[a["tn"],a["fp"],a["fn"],a["tp"]]
    fig,ax=plt.subplots()
    ax.bar(labels,vals)
    ax.set_ylabel("TE count")
    ax.set_title("Human vs model cultural abstention")
    ax.tick_params(axis="x",rotation=25)
    fig.tight_layout()
    fig.savefig(outdir/"fig01_abstention_confusion.png",dpi=180)
    fig.savefig(outdir/"fig01_abstention_confusion.pdf")
    plt.close(fig)

    # 2 facet prevalence human vs model
    human_counts=Counter()
    model_counts=Counter()
    for r in det["te_facet"]["rows"]:
        for fc in filter(None,r["human_facets"].split(";")): human_counts[fc]+=1
        for fc in filter(None,r["model_facets"].split(";")): model_counts[fc]+=1
    x=list(FACETS)
    xs=list(range(len(x)))
    fig,ax=plt.subplots()
    width=.38
    ax.bar([i-width/2 for i in xs],[human_counts[fc] for fc in x],width,label="Human")
    ax.bar([i+width/2 for i in xs],[model_counts[fc] for fc in x],width,label="Model")
    ax.set_xticks(xs,[fc for fc in x])
    ax.set_ylabel("TE count")
    ax.set_title("Supported facet prevalence in the 105-TE evaluation sample")
    ax.legend()
    fig.tight_layout()
    fig.savefig(outdir/"fig02_facet_prevalence_human_model.png",dpi=180)
    fig.savefig(outdir/"fig02_facet_prevalence_human_model.pdf")
    plt.close(fig)

    # 3 per-facet F1
    pf=det["te_facet"]["per_facet_unweighted"]
    fig,ax=plt.subplots()
    ax.bar([r["facet_code"] for r in pf],[0 if r["f1"] is None or not (r["f1"]==r["f1"]) else r["f1"] for r in pf])
    ax.set_ylim(0,1)
    ax.set_ylabel("F1")
    ax.set_title("TE-level facet F1 by cultural facet")
    fig.tight_layout()
    fig.savefig(outdir/"fig03_te_facet_f1.png",dpi=180)
    fig.savefig(outdir/"fig03_te_facet_f1.pdf")
    plt.close(fig)

    # 4 salience confusion heatmap
    mat=[[det["salience"]["confusion_unweighted"].get((i,j),0) for j in [1,2,3]] for i in [1,2,3]]
    fig,ax=plt.subplots()
    im=ax.imshow(mat)
    ax.set_xticks([0,1,2],["1","2","3"]); ax.set_yticks([0,1,2],["1","2","3"])
    ax.set_xlabel("Model salience"); ax.set_ylabel("Human salience")
    ax.set_title("Salience agreement on common supported facets")
    for i in range(3):
        for j in range(3):
            ax.text(j,i,str(mat[i][j]),ha="center",va="center")
    fig.colorbar(im,ax=ax)
    fig.tight_layout()
    fig.savefig(outdir/"fig04_salience_confusion.png",dpi=180)
    fig.savefig(outdir/"fig04_salience_confusion.pdf")
    plt.close(fig)

    # 5 coverage error histogram
    errs=[r["coverage_abs_error"] for r in det["coverage"]["rows"] if r["coverage_abs_error"] is not None]
    fig,ax=plt.subplots()
    ax.hist(errs,bins=10)
    ax.set_xlabel("Absolute Coverage error")
    ax.set_ylabel("TE-facet pair count")
    ax.set_title("Primary Coverage error distribution")
    fig.tight_layout()
    fig.savefig(outdir/"fig05_coverage_error.png",dpi=180)
    fig.savefig(outdir/"fig05_coverage_error.pdf")
    plt.close(fig)

    # 6 component count diagnostic
    diffs=[r["signed_difference_model_minus_human"] for r in det["component_count"]["rows"]]
    fig,ax=plt.subplots()
    ax.hist(diffs,bins=range(int(min(diffs))-1,int(max(diffs))+2))
    ax.set_xlabel("Model eligible component count − human eligible component count")
    ax.set_ylabel("TE count")
    ax.set_title("Eligible component-count difference")
    fig.tight_layout()
    fig.savefig(outdir/"fig06_component_count_difference.png",dpi=180)
    fig.savefig(outdir/"fig06_component_count_difference.pdf")
    plt.close(fig)

    if full:
        c=full["component_extraction_primary_eligible_weighted"]
        fig,ax=plt.subplots()
        ax.bar(["Precision","Recall","F1"],[c["precision"],c["recall"],c["f1"]])
        ax.set_ylim(0,1)
        ax.set_title("Eligible component extraction — weighted")
        fig.tight_layout()
        fig.savefig(outdir/"fig07_component_extraction_prf.png",dpi=180)
        fig.savefig(outdir/"fig07_component_extraction_prf.pdf")
        plt.close(fig)

        # assertion confusion weighted
        conf=full["assertion_state_weighted"]["confusion"]
        mat=[[conf[a][b] for b in ASSERTION_STATES] for a in ASSERTION_STATES]
        fig,ax=plt.subplots()
        im=ax.imshow(mat)
        ax.set_xticks(range(len(ASSERTION_STATES)),ASSERTION_STATES)
        ax.set_yticks(range(len(ASSERTION_STATES)),ASSERTION_STATES)
        ax.set_xlabel("Model state"); ax.set_ylabel("Human state")
        ax.set_title("Assertion-state confusion — weighted")
        fig.colorbar(im,ax=ax)
        fig.tight_layout()
        fig.savefig(outdir/"fig08_assertion_state_confusion.png",dpi=180)
        fig.savefig(outdir/"fig08_assertion_state_confusion.pdf")
        plt.close(fig)

        g=full["semantic_grounding"]["counts"]
        fig,ax=plt.subplots()
        ax.bar(list(GROUNDING_LABELS),[g.get(k,0) for k in GROUNDING_LABELS])
        ax.set_ylabel("Predicted assertion count")
        ax.set_title("Human semantic-grounding review")
        fig.tight_layout()
        fig.savefig(outdir/"fig09_semantic_grounding.png",dpi=180)
        fig.savefig(outdir/"fig09_semantic_grounding.pdf")
        plt.close(fig)

def build_results_workbook(path: Path, metric_rows, issues, det, full):
    import xlsxwriter
    wb=xlsxwriter.Workbook(str(path))
    title=wb.add_format({"bold":True,"font_size":15,"font_color":"#FFFFFF","bg_color":"#1F4E78"})
    head=wb.add_format({"bold":True,"font_color":"#FFFFFF","bg_color":"#4472C4","border":1,"text_wrap":True})
    cell=wb.add_format({"border":1,"text_wrap":True,"valign":"top"})
    pct=wb.add_format({"border":1,"num_format":"0.000","valign":"top"})
    warn=wb.add_format({"border":1,"bg_color":"#FFF2CC","text_wrap":True})

    ws=wb.add_worksheet("Summary")
    ws.merge_range("A1:E1","CP13 Human vs Frozen Model Evaluation",title)
    headers=["family","metric","unweighted","weighted","denominator_or_note"]
    ws.write_row(2,0,headers,head)
    for i,r in enumerate(metric_rows,3):
        ws.write(i,0,r["family"],cell); ws.write(i,1,r["metric"],cell)
        for c,k in [(2,"unweighted"),(3,"weighted")]:
            v=r[k]
            if v is None: ws.write_blank(i,c,None,cell)
            else: ws.write_number(i,c,float(v),pct)
        ws.write(i,4,r["denominator_or_note"],cell)
    ws.set_column("A:B",34); ws.set_column("C:D",16); ws.set_column("E:E",80)

    ws=wb.add_worksheet("Validation")
    ih=["severity","code","eval_id","item_id","detail"]
    ws.write_row(0,0,ih,head)
    for i,r in enumerate(issues,1): ws.write_row(i,0,[r.get(k,"") for k in ih],warn if r.get("severity")!="INFO" else cell)
    for c,w in enumerate([14,38,14,28,100]): ws.set_column(c,c,w)

    def add_rows(name,rows):
        ws=wb.add_worksheet(name[:31])
        if not rows: return
        hs=list(rows[0].keys()); ws.write_row(0,0,hs,head)
        for i,r in enumerate(rows,1): ws.write_row(i,0,[safe(r.get(k)) for k in hs],cell)
        ws.freeze_panes(1,1)
        ws.autofilter(0,0,len(rows),len(hs)-1)
        for c in range(len(hs)): ws.set_column(c,c,22)
    add_rows("TE_Facet",det["te_facet"]["rows"])
    add_rows("Per_Facet_Unweighted",det["te_facet"]["per_facet_unweighted"])
    add_rows("Per_Facet_Weighted",det["te_facet"]["per_facet_weighted"])
    add_rows("Salience_Pairs",det["salience"]["pairs"])
    add_rows("Coverage_Pairs",det["coverage"]["rows"])
    add_rows("Component_Count",det["component_count"]["rows"])
    if full:
        add_rows("Component_Matching",full["component_rows"])
        add_rows("Component_S1_Facet",full["component_s1_facet_primary_per_facet"])
        add_rows("Assertion_Matching",full["assertion_match_rows"])
    wb.close()

def make_report(outdir: Path, issues, ctx, det, full):
    blocker=[x for x in issues if x["severity"]=="BLOCKER"]
    pending=[x for x in issues if x["severity"]=="PENDING"]
    lines=[
        "# CP13 Final Human vs Frozen-Model Evaluation",
        "",
        "## Evaluation status",
        "",
        f"- Human TE count: {len(det['abstention']['rows'])}",
        f"- Human gold components: {det['human_summary']['gold_components']}",
        f"- Human gold assertions: {det['human_summary']['gold_assertions']}",
        f"- Human cultural abstentions: {det['human_summary']['human_abstentions']}",
        f"- Blocking validation issues: {len(blocker)}",
        f"- Pending model-review issues: {len(pending)}",
        "",
        "The 105-TE human sample is outcome-stratified among technically accepted CP11 outputs. "
        "Unweighted results describe the designed 105-TE evaluation sample. Weighted results use "
        "the frozen inverse-probability sampling weights and target the 643 technically accepted CP11 outputs. "
        "Technical failure robustness for all 1,441 TEs remains a separate CP11/CP12 result.",
        "",
        "## Deterministic metrics available without model-review matching",
        "",
    ]
    a=det["abstention"]
    lines += [
        f"- Weighted abstention-status accuracy: {a['weighted']['accuracy']:.3f}",
        f"- Weighted correctness/precision of model abstention: {a['weighted']['abstention_precision']:.3f}",
        f"- TE-level facet weighted micro Precision / Recall / F1: "
        f"{det['te_facet']['weighted']['precision']:.3f} / "
        f"{det['te_facet']['weighted']['recall']:.3f} / "
        f"{det['te_facet']['weighted']['f1']:.3f}",
        f"- TE-level facet weighted exact-set agreement: {det['te_facet']['weighted']['exact_set_agreement']:.3f}",
        f"- Salience weighted QWK / MAE / exact / within-one: "
        f"{det['salience']['weighted']['qwk']:.3f} / "
        f"{det['salience']['weighted']['mae']:.3f} / "
        f"{det['salience']['weighted']['exact_agreement']:.3f} / "
        f"{det['salience']['weighted']['within_one_agreement']:.3f}",
        f"- Primary Coverage weighted MAE: {det['coverage']['weighted']['coverage_mae']:.3f}",
        f"- Coverage weighted exact numerator / denominator agreement: "
        f"{det['coverage']['weighted']['exact_numerator_agreement']:.3f} / "
        f"{det['coverage']['weighted']['exact_denominator_agreement']:.3f}",
        "",
    ]
    if full:
        lines += [
            "## Matching-dependent metrics",
            "",
            f"- Eligible component extraction weighted P/R/F1: "
            f"{full['component_extraction_primary_eligible_weighted']['precision']:.3f} / "
            f"{full['component_extraction_primary_eligible_weighted']['recall']:.3f} / "
            f"{full['component_extraction_primary_eligible_weighted']['f1']:.3f}",
            f"- Primary component-level S1 facet weighted P/R/F1: "
            f"{full['component_s1_facet_primary_weighted']['precision']:.3f} / "
            f"{full['component_s1_facet_primary_weighted']['recall']:.3f} / "
            f"{full['component_s1_facet_primary_weighted']['f1']:.3f}",
            f"- Assertion-state weighted accuracy / macro-F1 (observed states): "
            f"{full['assertion_state_weighted']['accuracy']:.3f} / "
            f"{full['assertion_state_weighted']['macro_f1']:.3f}",
            "",
        ]
    else:
        lines += [
            "## Metrics still pending",
            "",
            "Component extraction P/R/F1, primary component-level S1 facet P/R/F1, "
            "assertion-state accuracy/macro-F1, and semantic-grounding rates require the "
            "post-blind model-review mappings/judgments. The evaluator intentionally does not "
            "invent those semantic matches automatically.",
            "",
        ]
    if blocker or pending:
        lines += ["## Validation / review items", ""]
        for x in (blocker+pending)[:100]:
            lines.append(f"- {x['severity']} `{x['code']}` {x.get('eval_id','')} {x.get('item_id','')}: {x.get('detail','')}")
        if len(blocker)+len(pending)>100:
            lines.append("- See `tables/validation_issues.csv` for the complete list.")
    (outdir/"CP13_EVALUATION_REPORT.md").write_text("\n".join(lines)+"\n",encoding="utf-8")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--human",type=Path,required=True)
    ap.add_argument("--model",type=Path,required=True)
    ap.add_argument("--out-dir",type=Path,required=True)
    ap.add_argument("--allow-human-evidence-warning",action="store_true",
                    help="Allow deterministic partial results even when the human workbook has an ambiguous/zero exact-evidence span. Full results remain non-final.")
    args=ap.parse_args()

    out=args.out_dir.resolve()
    if out.exists():
        raise SystemExit(f"Refusing to overwrite existing evaluation directory: {out}")
    out.mkdir(parents=True)

    data=load_inputs(args.human.resolve(),args.model.resolve())
    issues,ctx=validate(data)

    # Check sample hash from workbook metadata/selection if present.
    meta = {r["Field"]:r["Value"] for r in data["human_metadata"]}
    if meta.get("Sample manifest SHA-256") != EXPECTED_SAMPLE_SHA:
        issues.append({"severity":"BLOCKER","code":"human_sample_sha_mismatch","eval_id":"","item_id":"","detail":str(meta.get("Sample manifest SHA-256"))})

    det=evaluate_deterministic(data,ctx)

    human_blockers=[x for x in issues if x["severity"]=="BLOCKER"]
    evidence_only=all(x["code"] in {"human_evidence_ambiguous_duplicate","human_evidence_zero_match"} for x in human_blockers) if human_blockers else False

    full=None
    full_issues=[]
    if not human_blockers:
        full,full_issues=evaluate_full(data,ctx)
    elif args.allow_human_evidence_warning and evidence_only:
        # Keep partial deterministic outputs but do not declare full results.
        pass
    issues.extend(full_issues)

    tables=out/"tables"; figs=out/"figures"
    tables.mkdir(); figs.mkdir()

    write_csv(tables/"validation_issues.csv",issues,["severity","code","eval_id","item_id","detail"])
    write_csv(tables/"abstention_rows.csv",det["abstention"]["rows"])
    write_csv(tables/"te_facet_rows.csv",det["te_facet"]["rows"])
    write_csv(tables/"per_facet_unweighted.csv",det["te_facet"]["per_facet_unweighted"])
    write_csv(tables/"per_facet_weighted.csv",det["te_facet"]["per_facet_weighted"])
    write_csv(tables/"salience_pairs.csv",det["salience"]["pairs"])
    write_csv(tables/"coverage_pairs.csv",det["coverage"]["rows"])
    write_csv(tables/"component_count_diagnostic.csv",det["component_count"]["rows"])

    if full:
        write_csv(tables/"component_matching.csv",full["component_rows"])
        write_csv(tables/"component_s1_facet_primary.csv",full["component_s1_facet_primary_per_facet"])
        write_csv(tables/"assertion_matching.csv",full["assertion_match_rows"])

    metric_rows=build_metric_rows(det,full)
    write_csv(tables/"overall_metrics.csv",metric_rows)

    summary={
        "status": "FULL" if full else ("PARTIAL_WITH_HUMAN_EVIDENCE_WARNING" if human_blockers else "PARTIAL_MODEL_REVIEW_PENDING"),
        "human_file": str(args.human.resolve()),
        "model_file": str(args.model.resolve()),
        "human_sha256": hashlib.sha256(args.human.read_bytes()).hexdigest(),
        "model_sha256": hashlib.sha256(args.model.read_bytes()).hexdigest(),
        "sample_manifest_sha256": EXPECTED_SAMPLE_SHA,
        "validation_issue_count": len(issues),
        "blocking_issue_count": sum(x["severity"]=="BLOCKER" for x in issues),
        "review_summary": ctx["review_summary"],
        "deterministic": jsonable(det),
        "full": jsonable(full),
    }
    (out/"evaluation_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    make_charts(figs,det,full)
    build_results_workbook(out/"CP13_EVALUATION_RESULTS.xlsx",metric_rows,issues,det,full)
    make_report(out,issues,ctx,det,full)

    print("PASS: CP13 evaluator executed")
    print(f"STATUS={summary['status']}")
    print(f"OUT_DIR={out}")
    print(f"BLOCKING_ISSUES={summary['blocking_issue_count']}")
    print(f"TOTAL_ISSUES={summary['validation_issue_count']}")
    print(f"HUMAN_GOLD_COMPONENTS={det['human_summary']['gold_components']}")
    print(f"HUMAN_GOLD_ASSERTIONS={det['human_summary']['gold_assertions']}")
    print(f"HUMAN_ABSTENTIONS={det['human_summary']['human_abstentions']}")
    print("MODEL_REVIEW_SUMMARY=" + json.dumps(ctx["review_summary"],sort_keys=True))
    print()
    print("DETERMINISTIC WEIGHTED METRICS:")
    print(f"ABSTENTION_ACCURACY={det['abstention']['weighted']['accuracy']:.6f}")
    print(f"TE_FACET_P={det['te_facet']['weighted']['precision']:.6f}")
    print(f"TE_FACET_R={det['te_facet']['weighted']['recall']:.6f}")
    print(f"TE_FACET_F1={det['te_facet']['weighted']['f1']:.6f}")
    print(f"SALIENCE_QWK={det['salience']['weighted']['qwk']:.6f}")
    print(f"SALIENCE_MAE={det['salience']['weighted']['mae']:.6f}")
    print(f"COVERAGE_MAE={det['coverage']['weighted']['coverage_mae']:.6f}")
    if full:
        print()
        print("FULL MATCHING-DEPENDENT METRICS AVAILABLE=YES")
    else:
        print()
        print("FULL MATCHING-DEPENDENT METRICS AVAILABLE=NO")
        print("Reason: fix human validation blockers and/or complete the minimal model-review fields.")

if __name__=="__main__":
    main()
