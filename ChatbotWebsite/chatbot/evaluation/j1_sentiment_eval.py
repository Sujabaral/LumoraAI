# ChatbotWebsite/chatbot/evaluation/j1_sentiment_eval.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sklearn.metrics import classification_report, confusion_matrix

from ChatbotWebsite import db
from ChatbotWebsite.models import ChatHistory, EvalDataset, EvalDatasetItem

LABELS = ["negative", "neutral", "positive"]
_ALLOWED = set(LABELS)

# Only keep safe aliases (your DB already stores proper strings)
_LABEL_MAP = {
    "neg": "negative",
    "negative": "negative",
    "neu": "neutral",
    "neutral": "neutral",
    "pos": "positive",
    "positive": "positive",
}


def _normalize_label(x: Any) -> Optional[str]:
    if x is None:
        return None
    s = str(x).strip().lower().replace('"', "").replace("'", "")
    s = _LABEL_MAP.get(s, s)
    return s if s in _ALLOWED else None


def _macro_f1(rep: Dict[str, Any]) -> float:
    try:
        return float(rep["macro avg"]["f1-score"])
    except Exception:
        return 0.0


def _label_from_vader(v: float) -> str:
    # Standard VADER cutoffs
    if v >= 0.05:
        return "positive"
    if v <= -0.05:
        return "negative"
    return "neutral"


def _label_from_score(s: float, pos_thr: float = 0.60, neg_thr: float = 0.40) -> str:
    """
    Convert a 0..1 score (probability/normalized score) into label.
    Assumption:
      - higher => more positive
      - lower => more negative
      - middle => neutral
    """
    if s >= pos_thr:
        return "positive"
    if s <= neg_thr:
        return "negative"
    return "neutral"


def _zero_cm() -> List[List[int]]:
    return [[0, 0, 0], [0, 0, 0], [0, 0, 0]]


def _safe_report(y_true: List[str], y_pred: List[str]) -> Tuple[float, List[List[int]]]:
    if not y_true:
        return 0.0, _zero_cm()
    rep = classification_report(y_true, y_pred, labels=LABELS, output_dict=True, zero_division=0)
    cm = confusion_matrix(y_true, y_pred, labels=LABELS).tolist()
    return _macro_f1(rep), cm


def _resolve_dataset(dataset_id: Optional[int]) -> Tuple[Optional[EvalDataset], str]:
    """
    If dataset_id is provided -> use it.
    Else -> choose the dataset with the MOST items (prefer frozen in tie).
    This prevents auto-selecting tiny datasets like id=1 with only 3 items.
    """
    if dataset_id is not None:
        ds = EvalDataset.query.filter_by(id=int(dataset_id)).first()
        return ds, "explicit"

    # Count items per dataset and pick the max.
    # Prefer frozen if counts tie.
    rows = (
        db.session.query(
            EvalDataset,
            db.func.count(EvalDatasetItem.id).label("n_items"),
        )
        .outerjoin(EvalDatasetItem, EvalDatasetItem.dataset_id == EvalDataset.id)
        .group_by(EvalDataset.id)
        .order_by(
            db.func.count(EvalDatasetItem.id).desc(),
            EvalDataset.is_frozen.desc(),
            EvalDataset.id.desc(),
        )
        .all()
    )

    if not rows:
        return None, "none"

    ds = rows[0][0]
    return ds, "auto_max_items"


def evaluate_sentiment(
    dataset_id: Optional[int] = None,
    *,
    pos_thr: float = 0.60,
    neg_thr: float = 0.40,
    require_dataset: bool = True,
) -> Dict[str, Any]:
    """
    J1 Sentiment evaluation.

    Ground truth:
      - ChatHistory.human_label (your DB already has negative/neutral/positive)

    Predictions:
      - VADER: label from ChatHistory.vader_score
      - ML: label from ChatHistory.sentiment_score (fallback ml_prob, fallback final_score)
      - Hybrid: ChatHistory.sentiment_label (fallback label from final_score)

    Dataset behavior:
      - If dataset_id provided -> evaluate only items in that dataset
      - If dataset_id None -> auto-pick dataset with most items
      - If require_dataset=False -> evaluate across ALL human-labeled ChatHistory rows
        (useful if you want evaluation even without datasets)
    """
    ds, mode = _resolve_dataset(dataset_id)

    if require_dataset:
        if not ds:
            return {
                "f1": {"vader": 0.0, "ml": 0.0, "hybrid": 0.0},
                "labels": LABELS,
                "confusion": {"vader": _zero_cm(), "ml": _zero_cm(), "hybrid": _zero_cm()},
                "meta": {
                    "n_samples_gt": 0,
                    "n_vader": 0,
                    "n_ml": 0,
                    "n_hybrid": 0,
                    "distribution": {k: 0 for k in LABELS},
                    "dataset": {"requested": dataset_id, "resolved": None, "mode": mode},
                    "note": "No evaluation dataset found. Create a dataset first or set require_dataset=False.",
                },
            }
        dataset_id = int(ds.id)

        # Only rows included in this dataset
        base_q = (
            ChatHistory.query
            .join(EvalDatasetItem, ChatHistory.id == EvalDatasetItem.chat_history_id)
            .filter(EvalDatasetItem.dataset_id == dataset_id)
        )
    else:
        # All labeled rows (no dataset restriction)
        base_q = ChatHistory.query

    # Ground truth must exist
    rows = (
        base_q
        .filter(ChatHistory.human_label.isnot(None))
        .order_by(ChatHistory.id.asc())
        .all()
    )

    # Prepare containers
    y_true_all: List[str] = []

    vader_y_true: List[str] = []
    vader_pred: List[str] = []

    ml_y_true: List[str] = []
    ml_pred: List[str] = []

    hy_y_true: List[str] = []
    hybrid_pred: List[str] = []

    skipped_invalid_gt = 0

    for r in rows:
        gt = _normalize_label(r.human_label)
        if gt is None:
            skipped_invalid_gt += 1
            continue

        y_true_all.append(gt)

        # VADER model coverage
        if r.vader_score is not None:
            try:
                vader_y_true.append(gt)
                vader_pred.append(_label_from_vader(float(r.vader_score)))
            except Exception:
                pass

        # ML model coverage: prefer sentiment_score then ml_prob then final_score
        ml_score = r.sentiment_score
        if ml_score is None:
            ml_score = r.ml_prob
        if ml_score is None:
            ml_score = r.final_score

        if ml_score is not None:
            try:
                ml_y_true.append(gt)
                ml_pred.append(_label_from_score(float(ml_score), pos_thr=pos_thr, neg_thr=neg_thr))
            except Exception:
                pass

        # Hybrid coverage: prefer sentiment_label; else label from final_score
        hy = _normalize_label(r.sentiment_label)
        if hy is None and r.final_score is not None:
            try:
                hy = _label_from_score(float(r.final_score), pos_thr=pos_thr, neg_thr=neg_thr)
            except Exception:
                hy = None

        if hy is not None:
            hy_y_true.append(gt)
            hybrid_pred.append(hy if hy in _ALLOWED else "neutral")

    # Distribution over all usable GT
    dist = {lab: y_true_all.count(lab) for lab in LABELS}

    # Reports per-model (only where that model exists)
    f1_v, cm_v = _safe_report(vader_y_true, vader_pred)
    f1_m, cm_m = _safe_report(ml_y_true, ml_pred)
    f1_h, cm_h = _safe_report(hy_y_true, hybrid_pred)

    meta_ds = {
        "requested": dataset_id if require_dataset else dataset_id,
        "resolved": int(ds.id) if (require_dataset and ds) else None,
        "mode": mode,
    }
    if require_dataset and ds:
        meta_ds.update({
            "is_frozen": bool(getattr(ds, "is_frozen", False)),
            "name": getattr(ds, "name", ""),
        })

    note = (
        "J1 metrics computed on the selected evaluation dataset."
        if require_dataset
        else "J1 metrics computed on all human-labeled ChatHistory rows (no dataset filter)."
    )

    return {
        "f1": {"vader": f1_v, "ml": f1_m, "hybrid": f1_h},
        "labels": LABELS,
        "confusion": {"vader": cm_v, "ml": cm_m, "hybrid": cm_h},
        "meta": {
            "dataset": meta_ds,
            "n_samples_gt": len(y_true_all),
            "n_vader": len(vader_y_true),
            "n_ml": len(ml_y_true),
            "n_hybrid": len(hy_y_true),
            "distribution": dist,
            "skipped_invalid_gt": skipped_invalid_gt,
            "ground_truth": "ChatHistory.human_label",
            "note": note,
        },
    }