"""T33: the project's brand kit -- the one place the CLI and every API route load it from.

A project names its kit by id (`Project.brand_kit`). T39 lookup order: a library project's
company kit first (`<library>/<Company>/brand/`, id = the company name), then the repo's
`packages/brandkit/kits/` (`_demo`, the neutral kit tests and demos use; `_template` is not
a kit). Either holds a Brand System (`design-system/`) or a legacy `brand.yaml`. Projects
with no choice load `_demo`. `$POST3_KITS_DIR` points the whole app at another repo-kits
folder (tests use a temp one). Kit ids are matched against the listings, never joined onto a
path as given, so an id can't reach outside them.

`set_project_kit` records the choice and re-points every workflow at the new kit
(`recipes.rebrand`): branded nodes, and everything downstream of them, go stale -- old
outputs stay visible, and nothing is regenerated until someone asks.
"""
from __future__ import annotations

import os
from pathlib import Path

import brandkit
from brandkit.compile import writer_context
from brandkit.schema import BrandKit, BrandKitError
from brandkit.status import status_report

from .library import company_brand_dir, project_company
from .model.project import DEFAULT_BRAND_KIT
from .store import store as store_module
from .store.paths import store_root

KITS_DIR_ENV = "POST3_KITS_DIR"


class UnknownKit(ValueError):
    """No kit with that id under the kits folder; the message lists the ones there are."""

    def __init__(self, kit_id: str, available: list[str]) -> None:
        self.kit_id = kit_id
        self.available = available
        super().__init__(f"unknown brand kit {kit_id!r}; available: {', '.join(available) or '(none)'}")


def kits_root() -> Path:
    override = os.environ.get(KITS_DIR_ENV)
    if override:
        return Path(override).resolve()
    return Path(brandkit.__file__).resolve().parent.parent / "kits"


def _is_kit(path: Path) -> bool:
    return (path / "design-system" / "design-system.json").is_file() or (path / "brand.yaml").is_file()


def _repo_kits() -> list[str]:
    root = kits_root()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir()
                  if p.is_dir() and p.name[0] != "." and p.name != "_template" and _is_kit(p))


def _company_kit(project_root: str | Path | None, company: str | None = None) -> tuple[str, Path] | None:
    """`(company name, <Company>/brand)` when the project is in the library and its company
    has a kit; otherwise None. `company` names it for a project not created yet."""
    if project_root is None:
        return None
    company = company or project_company(project_root)
    if not company:
        return None
    brand_dir = company_brand_dir(project_root, company)
    if not _is_kit(brand_dir):
        return None
    return company, brand_dir


def available_kits(project_root: str | Path | None = None, company: str | None = None) -> list[str]:
    """The project's company kit (if any) first, then every repo kit, sorted. `_template`
    and dot-folders are not kits."""
    company = _company_kit(project_root, company)
    repo = _repo_kits()
    if company is None:
        return repo
    return [company[0], *(k for k in repo if k != company[0])]


def kit_dir(kit_id: str, project_root: str | Path | None = None, company: str | None = None) -> Path:
    found = _company_kit(project_root, company)
    if found is not None and kit_id == found[0]:
        return found[1]
    available = available_kits(project_root, company)
    if kit_id not in available:
        raise UnknownKit(kit_id, available)
    return kits_root() / kit_id


def load_kit(kit_id: str, project_root: str | Path | None = None) -> BrandKit:
    return BrandKit.load(kit_dir(kit_id, project_root))


def default_kit_id(project_root: str | Path, company: str | None = None) -> str:
    """What a new project uses when no kit is named: its company's kit, else `_demo`."""
    found = _company_kit(project_root, company)
    return found[0] if found is not None else DEFAULT_BRAND_KIT


def project_kit_id(project_root: str | Path) -> str:
    project, _rev = store_module.try_read(project_root, "project")
    return project.brand_kit if project is not None else DEFAULT_BRAND_KIT


def load_project_kit(project_root: str | Path) -> BrandKit:
    """The project's kit. Raises `UnknownKit` / `BrandKitError` (both `ValueError`s)."""
    return load_kit(project_kit_id(project_root), project_root)


def project_writer_context(project_root: str | Path) -> dict:
    """The project's kit as brief-writer context; `{}` when the kit can't be loaded (a
    brief can still be written without brand context, so this never blocks one)."""
    try:
        return writer_context(load_project_kit(project_root))
    except (UnknownKit, BrandKitError):
        return {}


def kit_summary(kit_id: str, project_root: str | Path | None = None) -> dict:
    """`{id, name, status, counts, error}` for a kit picker. `status` is `guessed` when any
    filled field is a first guess (`init --from`), `filled` when every filled field is
    confirmed, `broken` when the kit does not load."""
    try:
        kit = load_kit(kit_id, project_root)
    except (UnknownKit, BrandKitError) as exc:
        return {"id": kit_id, "name": kit_id, "status": "broken", "counts": None, "error": str(exc)}
    report = status_report(kit)
    counts = report["counts"]
    name = kit.core_identity_name.text if kit.core_identity_name.status == "filled" else None
    return {
        "id": kit_id, "name": name or kit_id, "status": "guessed" if counts["guessed"] else "filled",
        "counts": counts, "error": None,
    }


def list_kit_summaries(project_root: str | Path | None = None) -> list[dict]:
    return [kit_summary(k, project_root) for k in available_kits(project_root)]


def _workflow_ids(project_root: str | Path) -> list[str]:
    d = store_root(project_root) / "workflows"
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []


def set_project_kit(project_root: str | Path, kit_id: str) -> dict:
    """Make `kit_id` the project's kit and re-point every workflow at it. Refuses an unknown
    or unloadable kit before touching anything. Setting the same kit again re-hashes it, so
    edits to the kit since the workflows were built show up as stale too."""
    from .recipes.rebrand import rebrand_workflow

    kit = load_kit(kit_id, project_root)
    project, revision = store_module.read(project_root, "project")
    previous = project.brand_kit
    if previous != kit_id:
        store_module.write(project_root, "project", project.model_copy(update={"brand_kit": kit_id}),
                           expected_rev=revision)

    updated: list[str] = []
    unbranded: dict[str, list[str]] = {}
    for workflow_id in _workflow_ids(project_root):
        workflow, wf_rev = store_module.read(project_root, "workflow", workflow_id)
        new_workflow, left = rebrand_workflow(workflow, kit)
        if left:
            unbranded[workflow_id] = left
        if new_workflow != workflow:
            store_module.write(project_root, "workflow", new_workflow, expected_rev=wf_rev)
            updated.append(workflow_id)
    return {
        "brand_kit": kit_id, "previous": previous, "kit_hash": kit.kit_hash(),
        "workflows_updated": updated, "unbranded": unbranded,
    }


__all__ = [
    "KITS_DIR_ENV", "UnknownKit", "kits_root", "available_kits", "kit_dir", "load_kit", "default_kit_id",
    "project_kit_id", "load_project_kit", "project_writer_context", "kit_summary",
    "list_kit_summaries", "set_project_kit",
]
