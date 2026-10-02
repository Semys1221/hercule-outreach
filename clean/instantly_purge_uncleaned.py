"""Remove campaign leads whose emails are not MEV-valid per local cache artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

import pandas as pd

_LIB_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _LIB_DIR.parent
for path in (_REPO_ROOT, _LIB_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from bulk_verifier import normalize_status  # noqa: E402
from checkpoint import CHECKPOINT_SUFFIX, list_checkpoints  # noqa: E402
from clean_column import CLEANED_KEY, CLEANED_VALUE_VALID  # noqa: E402
from instantly_client import (  # noqa: E402
    InstantlyClient,
    _get_client,
    count_leads_in_campaign,
    wait_for_background_job,
)
from paths import data_dir  # noqa: E402
from shared import instantly_client as shared_instantly  # noqa: E402

# Instantly bulk DELETE accepts many ids but only processes ~50 per request (see API `count`).
_DELETE_BATCH_SIZE = 50
DEFAULT_ALLOWED_STATUSES = ("Valid", "Catch All")


def _log(msg: str) -> None:
    print(msg, flush=True)


def _parse_allowed_statuses(raw: str) -> frozenset[str]:
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    return frozenset(parts or DEFAULT_ALLOWED_STATUSES)


def _normalize_email(email: object) -> str:
    if email is None or (isinstance(email, float) and pd.isna(email)):
        return ""
    return str(email).strip().lower()


def _find_email_column(df: pd.DataFrame) -> str | None:
    for candidate in ("email", "Email"):
        if candidate in df.columns:
            return candidate
    lower = {col.lower(): col for col in df.columns}
    return lower.get("email")


def _emails_from_verified_csv(path: Path, allowed: frozenset[str]) -> set[str]:
    df = pd.read_csv(path)
    email_col = _find_email_column(df)
    if not email_col:
        raise ValueError(f"No email column in {path}")
    status_col = "Verification_Status"
    if status_col not in df.columns:
        raise ValueError(f"No {status_col!r} column in {path}")
    mask = df[status_col].apply(lambda s: normalize_status(s) in allowed)
    return {_normalize_email(e) for e in df.loc[mask, email_col] if _normalize_email(e)}


def _emails_from_final_clean_csv(path: Path) -> set[str]:
    df = pd.read_csv(path)
    email_col = _find_email_column(df)
    if not email_col:
        raise ValueError(f"No email column in {path}")
    return {_normalize_email(e) for e in df[email_col] if _normalize_email(e)}


def _emails_from_checkpoint_json(path: Path, allowed: frozenset[str]) -> set[str]:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    status_map = payload.get("status_map") or {}
    cleaned: set[str] = set()
    for email, status in status_map.items():
        normalized_email = _normalize_email(email)
        if not normalized_email:
            continue
        if normalize_status(status) in allowed:
            cleaned.add(normalized_email)
    return cleaned


def _prefix_from_path(path: Path) -> str | None:
    name = path.name
    for suffix in (
        CHECKPOINT_SUFFIX,
        "_final_clean.csv",
        "_verified.csv",
        "_verified_partial.csv",
    ):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return None


def resolve_mev_cleaned_emails(
    *,
    mev_path: str | None = None,
    mev_prefix: str | None = None,
    use_latest_checkpoint: bool = False,
    allowed_statuses: frozenset[str],
) -> tuple[set[str], list[str]]:
    """Return (cleaned email set, human-readable source paths used)."""
    sources: list[str] = []

    if mev_path:
        path = Path(mev_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"MEV artifact not found: {path}")
        sources.append(str(path))
        if path.name.endswith(CHECKPOINT_SUFFIX):
            return _emails_from_checkpoint_json(path, allowed_statuses), sources
        if path.name.endswith("_final_clean.csv"):
            return _emails_from_final_clean_csv(path), sources
        if path.name.endswith(("_verified.csv", "_verified_partial.csv")):
            return _emails_from_verified_csv(path, allowed_statuses), sources
        raise ValueError(
            f"Unsupported MEV artifact {path.name} "
            "(expected checkpoint.json, final_clean.csv, or verified*.csv)"
        )

    prefix = (mev_prefix or "").strip()
    if not prefix and use_latest_checkpoint:
        checkpoints = list_checkpoints()
        if not checkpoints:
            raise FileNotFoundError(f"No checkpoints in {data_dir()}")
        prefix = checkpoints[0]["prefix"]

    if prefix:
        base = Path(data_dir())
        final_clean = base / f"{prefix}_final_clean.csv"
        if final_clean.is_file():
            sources.append(str(final_clean))
            return _emails_from_final_clean_csv(final_clean), sources

        checkpoint = base / f"{prefix}{CHECKPOINT_SUFFIX}"
        if checkpoint.is_file():
            sources.append(str(checkpoint))
            return _emails_from_checkpoint_json(checkpoint, allowed_statuses), sources

        verified = base / f"{prefix}_verified.csv"
        if verified.is_file():
            sources.append(str(verified))
            return _emails_from_verified_csv(verified, allowed_statuses), sources

        raise FileNotFoundError(
            f"No MEV artifacts for prefix {prefix!r} under {base}"
        )

    raise ValueError(
        "Specify --mev-path, --mev-prefix, or --use-latest-checkpoint for MEV cleaned set"
    )


def is_mev_cleaned(email: str, cleaned_set: set[str]) -> bool:
    return _normalize_email(email) in cleaned_set


def is_cleaned_valid_on_instantly(lead: dict[str, Any]) -> bool:
    merged = InstantlyClient.lead_custom_variables(lead)
    value = merged.get(CLEANED_KEY)
    if value is None:
        return False
    return str(value).strip() == CLEANED_VALUE_VALID


def _lead_should_keep(
    lead: dict[str, Any],
    *,
    use_mev: bool,
    cleaned_emails: set[str],
) -> bool:
    if use_mev:
        return is_mev_cleaned(_lead_email(lead), cleaned_emails)
    return is_cleaned_valid_on_instantly(lead)


def _lead_id(lead: dict[str, Any]) -> str | None:
    raw = lead.get("id")
    if raw is None:
        return None
    lead_id = str(raw).strip()
    return lead_id or None


def _lead_email(lead: dict[str, Any]) -> str:
    return _normalize_email(lead.get("email"))


def fetch_all_campaign_leads(
    client: InstantlyClient,
    campaign_id: str,
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[dict[str, Any]]:
    return client.fetch_leads_from_campaign(
        campaign_id,
        max_leads=None,
        max_pages=10000,
        on_progress=on_progress,
    )


def bulk_delete_lead_ids(
    client: InstantlyClient,
    *,
    campaign_id: str,
    lead_ids: list[str],
    log_cb: Callable[[str], None] | None = None,
) -> dict[str, int]:
    """DELETE /leads with campaign_id + ids (Instantly API v2)."""
    stats = {"batches": 0, "requested": 0, "deleted": 0, "errors": 0}
    campaign = campaign_id.strip()
    for start in range(0, len(lead_ids), _DELETE_BATCH_SIZE):
        batch = [lid for lid in lead_ids[start : start + _DELETE_BATCH_SIZE] if lid]
        if not batch:
            continue
        stats["batches"] += 1
        stats["requested"] += len(batch)
        if log_cb:
            log_cb(
                f"Deleting batch {stats['batches']}: {len(batch)} lead(s) "
                f"({stats['requested']}/{len(lead_ids)})"
            )
        try:
            result = client._fetch(
                "/leads",
                method="DELETE",
                body={"campaign_id": campaign, "ids": batch},
            )
        except Exception as exc:
            stats["errors"] += len(batch)
            if log_cb:
                log_cb(f"Batch {stats['batches']} failed: {exc}")
            continue

        deleted = shared_instantly._read_delete_count(result)
        if deleted is not None:
            stats["deleted"] += deleted
        job_id = shared_instantly._read_job_id(result)
        if job_id:
            wait_for_background_job(job_id, log_cb=log_cb)

    return stats


def purge_uncleaned_from_campaign(
    campaign_id: str,
    *,
    cleaned_emails: set[str] | None = None,
    mev_sources: list[str] | None = None,
    use_mev: bool = False,
    dry_run: bool = True,
    log_cb: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    cid = campaign_id.strip()
    client = _get_client()
    mev_set = cleaned_emails or set()

    if log_cb:
        if use_mev:
            src = ", ".join(mev_sources or ["(inline set)"])
            log_cb(
                f"MEV cleaned cache: {len(mev_set)} email(s) from {src} "
                f"(allowed statuses applied at load time)"
            )
        else:
            log_cb(
                f"Keep rule: Instantly custom_variables.{CLEANED_KEY}=={CLEANED_VALUE_VALID!r}"
            )

    def progress(count: int, pages: int) -> None:
        if log_cb:
            log_cb(f"Listed {count} lead(s) ({pages} page(s))...")

    leads = fetch_all_campaign_leads(client, cid, on_progress=progress)
    kept: list[dict[str, Any]] = []
    remove: list[dict[str, Any]] = []
    for lead in leads:
        if _lead_should_keep(lead, use_mev=use_mev, cleaned_emails=mev_set):
            kept.append(lead)
        else:
            remove.append(lead)

    remove_ids = []
    for lead in remove:
        lid = _lead_id(lead)
        if lid:
            remove_ids.append(lid)

    sample_removed = [_lead_email(lead) for lead in remove[:10] if _lead_email(lead)]
    sample_kept = [_lead_email(lead) for lead in kept[:5] if _lead_email(lead)]

    stats: dict[str, Any] = {
        "total": len(leads),
        "kept": len(kept),
        "to_remove": len(remove),
        "remove_with_id": len(remove_ids),
        "removed": 0,
        "errors": 0,
        "mev_cleaned_count": len(mev_set) if use_mev else None,
        "mev_sources": mev_sources or [],
        "keep_mode": "mev" if use_mev else "instantly_cleaned_valid",
        "sample_removed_emails": sample_removed,
        "sample_kept_emails": sample_kept,
    }

    if log_cb:
        kept_label = "MEV cleaned" if use_mev else f"{CLEANED_KEY}={CLEANED_VALUE_VALID}"
        remove_label = "not in MEV cache" if use_mev else "missing/other cleaned tag"
        log_cb(
            f"Campaign {cid}: total={stats['total']}, "
            f"kept ({kept_label})={stats['kept']}, "
            f"to remove ({remove_label})={stats['to_remove']}"
        )
        if sample_kept:
            log_cb(f"Sample kept emails: {sample_kept}")
        if sample_removed:
            log_cb(f"Sample emails to remove ({len(sample_removed)}): {sample_removed}")

    if dry_run:
        if log_cb:
            log_cb("Dry-run: no leads deleted.")
        return stats

    if not remove_ids:
        if log_cb:
            log_cb("Nothing to delete.")
        return stats

    pass_num = 0
    total_deleted = 0
    while remove_ids:
        pass_num += 1
        if log_cb:
            log_cb(f"Delete pass {pass_num}: {len(remove_ids)} uncleaned lead(s) queued")
        delete_stats = bulk_delete_lead_ids(
            client,
            campaign_id=cid,
            lead_ids=remove_ids,
            log_cb=log_cb,
        )
        stats["errors"] += delete_stats["errors"]
        pass_deleted = delete_stats["deleted"]
        total_deleted += pass_deleted
        if pass_deleted <= 0:
            if log_cb:
                log_cb("Delete pass returned count=0 — stopping to avoid a loop.")
            break
        if log_cb:
            log_cb(f"Delete pass {pass_num}: API reported {pass_deleted} deleted")
        leads = fetch_all_campaign_leads(client, cid)
        remove_ids = [
            lid
            for lead in leads
            if not _lead_should_keep(lead, use_mev=use_mev, cleaned_emails=mev_set)
            for lid in (_lead_id(lead),)
            if lid
        ]
        stats["kept"] = sum(
            1
            for lead in leads
            if _lead_should_keep(lead, use_mev=use_mev, cleaned_emails=mev_set)
        )
        stats["to_remove"] = len(remove_ids)

    after_count = count_leads_in_campaign(cid)
    stats["remaining_after"] = after_count
    stats["removed"] = total_deleted
    if log_cb:
        log_cb(
            f"Done: API deleted {total_deleted} lead(s), "
            f"{after_count} remaining in campaign (~{stats['kept']} kept)"
        )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Remove Instantly campaign leads without cleaned=valid on Instantly "
            "(default), or not in local MEV cache when --mev-path / --mev-prefix / "
            "--use-latest-checkpoint is set."
        ),
    )
    parser.add_argument(
        "campaign_id",
        nargs="?",
        default=None,
        help="Instantly campaign UUID (or use --campaign-id)",
    )
    parser.add_argument(
        "--campaign-id",
        dest="campaign_id_flag",
        default=None,
        help="Instantly campaign UUID",
    )
    parser.add_argument(
        "--mev-path",
        default=None,
        help="Path to MEV artifact (checkpoint.json, final_clean.csv, verified.csv)",
    )
    parser.add_argument(
        "--mev-prefix",
        default=None,
        help=f"Artifact prefix under {data_dir()} (uses final_clean, else checkpoint, else verified)",
    )
    parser.add_argument(
        "--use-latest-checkpoint",
        action="store_true",
        help="Use the newest checkpoint prefix in clean/data",
    )
    parser.add_argument(
        "--allowed-statuses",
        default=",".join(DEFAULT_ALLOWED_STATUSES),
        help="Comma-separated MEV statuses that count as cleaned (for checkpoint/verified)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete uncleaned leads (default: dry-run only)",
    )
    parser.add_argument(
        "--mark-cleaned-on-instantly",
        action="store_true",
        help="After purge, PATCH kept leads with cleaned=valid on Instantly (optional)",
    )
    args = parser.parse_args()
    campaign_id = args.campaign_id_flag or args.campaign_id
    if not campaign_id:
        parser.error("campaign_id positional argument or --campaign-id is required")

    use_mev = bool(
        args.mev_path or args.mev_prefix or args.use_latest_checkpoint
    )
    cleaned_emails: set[str] | None = None
    mev_sources: list[str] = []
    if use_mev:
        allowed = _parse_allowed_statuses(args.allowed_statuses)
        cleaned_emails, mev_sources = resolve_mev_cleaned_emails(
            mev_path=args.mev_path,
            mev_prefix=args.mev_prefix,
            use_latest_checkpoint=args.use_latest_checkpoint,
            allowed_statuses=allowed,
        )

    stats = purge_uncleaned_from_campaign(
        campaign_id,
        cleaned_emails=cleaned_emails,
        mev_sources=mev_sources,
        use_mev=use_mev,
        dry_run=not args.execute,
        log_cb=_log,
    )

    if args.execute and args.mark_cleaned_on_instantly and stats.get("kept", 0) > 0:
        prefix = None
        if args.mev_prefix:
            prefix = args.mev_prefix.strip()
        elif args.mev_path:
            prefix = _prefix_from_path(Path(args.mev_path).resolve())
        if prefix:
            final_clean = Path(data_dir()) / f"{prefix}_final_clean.csv"
            if final_clean.is_file():
                from instantly_mark_cleaned import mark_cleaned_leads_in_instantly

                _log(f"Marking cleaned=valid on Instantly from {final_clean}...")
                df = pd.read_csv(final_clean)
                mark_stats = mark_cleaned_leads_in_instantly(
                    df,
                    campaign_id=campaign_id,
                )
                _log(f"Instantly mark cleaned stats: {mark_stats}")
            else:
                _log("--mark-cleaned-on-instantly skipped: no final_clean CSV for prefix")
        else:
            _log("--mark-cleaned-on-instantly skipped: could not resolve artifact prefix")

    _log(f"Summary: {stats}")


if __name__ == "__main__":
    main()
