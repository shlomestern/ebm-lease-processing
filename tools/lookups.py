"""
Lookups a lease draft needs: rooms, the approving admin, and the project's
auto-deposit address.

These used to live in spreadsheets in Shlome's Downloads folder, which a cloud
session cannot reach. The data is in data/ so an unattended run can use it.

Every lookup raises rather than guessing. A wrong room count or a wrong payment
address is worse than a stopped draft.
"""
import csv
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")


class LookupError_(Exception):
    """Raised when a value cannot be established. Never fall back to a guess."""


def _rows(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def _norm(s):
    """Loose comparison for addresses: case, punctuation and spacing vary."""
    s = (s or "").lower()
    s = s.replace("boulevard", "boul").replace("avenue", "ave").replace("street", "st")
    s = re.sub(r"[.,'’-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _street_number(s):
    """Leading civic number of an address, e.g. '12200 Boul de Pierrefonds' -> '12200'."""
    m = re.match(r"\s*(\d+)", s or "")
    return m.group(1) if m else None


def find_unit(project, address, unit):
    """Return the directory row for a unit, or raise if it is not unambiguous."""
    project, unit = str(project).strip(), str(unit).strip()
    rows = [r for r in _rows("apartments.csv")
            if r["project"].strip() == project and r["unit"].strip() == unit]
    if not rows:
        raise LookupError_(f"unit {unit} not found in project {project}")
    if len(rows) > 1 and address:
        # The street number is what separates buildings in a project (12200 vs
        # 12210 Pierrefonds), and it is the one part written the same way in a
        # request email and in the directory's full postal address.
        want_no = _street_number(address)
        narrowed = [r for r in rows if _street_number(r["property_address"]) == want_no] if want_no else []
        if not narrowed:
            want = _norm(address)
            narrowed = [r for r in rows
                        if want in _norm(r["property_address"]) or _norm(r["property_address"]) in want]
        if narrowed:
            rows = narrowed
    if len(rows) > 1:
        found = sorted({r["property_address"] for r in rows})
        raise LookupError_(
            f"unit {unit} appears in {len(rows)} buildings of project {project} "
            f"({', '.join(found)}) — pass the address to disambiguate")
    return rows[0]


def rooms_for(project, address, unit):
    """Rooms for a unit. '?' in the directory means look it up in Buildium."""
    row = find_unit(project, address, unit)
    rooms = (row.get("rooms") or "").strip()
    if rooms and rooms != "?":
        return rooms
    size = (row.get("size") or "").strip()
    if size:
        try:
            return str(float(size) + 0.5)      # rooms = size + 0.5
        except ValueError:
            pass
    raise LookupError_(
        f"rooms unknown for project {project} unit {unit} "
        f"({row.get('property_address','')}) — check Buildium and update data/apartments.csv")


def admin_for(project):
    """The admin who approves this project's leases, and how to reach them."""
    project = str(project).strip()
    for r in _rows("admins.csv"):
        if r["project"].strip() == project:
            if not r["email"].strip():
                raise LookupError_(
                    f"project {project}'s admin ({r['admin']}) has no email on file — "
                    f"cannot send for verification")
            return {"admin": r["admin"], "email": r["email"], "cell": r["cell"]}
    raise LookupError_(f"no admin listed for project {project}")


def auto_deposit_for(project):
    """The project's e-transfer address. Never invent one."""
    project = str(project).strip()
    for r in _rows("auto_deposit.csv"):
        if r["project"].strip() == project:
            if not r["email"].strip():
                raise LookupError_(f"project {project} has no auto-deposit address on file")
            return {"display_name": r["display_name"], "email": r["email"]}
    raise LookupError_(f"no auto-deposit address for project {project} — do not guess one")


BUILDING_RULES = {
    "EN": os.path.join(os.path.dirname(HERE), "forms", "building-rules", "Building rules E.pdf"),
    "FR": os.path.join(os.path.dirname(HERE), "forms", "building-rules", "Building rules F.pdf"),
}


def building_rules(lang):
    """Path to the building-rules PDF uploaded in Section E."""
    path = BUILDING_RULES.get(lang)
    if not path or not os.path.exists(path):
        raise LookupError_(f"no building rules PDF for language {lang!r}")
    return path
