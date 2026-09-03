"""
Fill the EFT and Hydro annexes for one lease.

Used by the lease routine after it has created the lease in CORPIQ, so the
CORPIQ lease number is known. Writes finished PDFs ready to attach as annexes.

    from tools.fill_forms import fill_eft, fill_hydro, HYDRO_PROJECTS

    eft = fill_eft("42", "EN", {
        "tenant_name": "Amina Abubakar",
        "building": "12200 Pierrefonds",
        "unit": "5",
        "tel": "514-555-0199",
        "rent_amount": "1,450.00",
        "start_date": "1 October 2026",
    }, out_dir)

Banking fields, the signature and its date are deliberately left empty: the
tenant cannot enter bank details in CORPIQ, which is why they are asked to
email a void cheque instead.
"""
import os
from pypdf import PdfReader, PdfWriter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
EFT_DIR = os.path.join(REPO, "forms", "eft")
HYDRO_DIR = os.path.join(REPO, "forms", "hydro")

# Only these projects have a Hydro addendum.
HYDRO_PROJECTS = {"13", "14", "17", "22", "24", "28", "30", "31", "32",
                  "33", "34", "38", "40", "42", "50"}

EFT_TENANT_FIELDS = {
    "tenant_name", "building", "unit", "tel",
    "rent_amount", "start_date", "first_amount", "date",
}
# Left for the tenant to complete by hand.
EFT_LEAVE_BLANK = (
    {f"account_{i}" for i in range(1, 11)}
    | {f"transit_{i}" for i in range(1, 6)}
    | {f"institution_{i}" for i in range(1, 4)}
    | {"institution_name", "signature_date"}
)


class FormError(Exception):
    """Raised when a form cannot be filled correctly. Never attach on this."""


def _write(template, values, out_path):
    reader = PdfReader(template)
    fields = set(reader.get_fields() or {})

    unknown = set(values) - fields
    if unknown:
        raise FormError(f"{os.path.basename(template)}: no such field(s): {sorted(unknown)}")

    writer = PdfWriter(clone_from=template)
    for page in writer.pages:
        writer.update_page_form_field_values(page, values)
    writer.set_need_appearances_writer(True)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as fh:
        writer.write(fh)

    # Read back: every value must have landed, and nothing else may be set.
    got = PdfReader(out_path).get_fields() or {}
    for k, v in values.items():
        actual = got.get(k, {}).get("/V")
        if str(actual or "") != str(v):
            raise FormError(f"{os.path.basename(out_path)}: {k!r} is {actual!r}, expected {v!r}")
    return out_path


def fill_eft(project, lang, values, out_dir):
    """Fill the EFT for a project. lang is 'EN' or 'FR'."""
    if lang not in ("EN", "FR"):
        raise FormError(f"lang must be EN or FR, got {lang!r}")
    template = os.path.join(EFT_DIR, f"{project} - EFT - {lang}.pdf")
    if not os.path.exists(template):
        raise FormError(f"no EFT template for project {project} — add it before drafting")

    unexpected = set(values) - EFT_TENANT_FIELDS
    if unexpected:
        raise FormError(f"these EFT fields are the tenant's to fill: {sorted(unexpected)}")
    for required in ("tenant_name", "building", "unit"):
        if not values.get(required):
            raise FormError(f"EFT needs {required}")

    out = _write(template, values, os.path.join(out_dir, f"EFT - {lang}.pdf"))

    blank = PdfReader(out).get_fields() or {}
    filled = [k for k in EFT_LEAVE_BLANK if blank.get(k, {}).get("/V")]
    if filled:
        raise FormError(f"banking/signature fields must stay empty, but got: {sorted(filled)}")
    return out


def fill_hydro(project, lease_number, address, tenant_name, date, out_dir):
    """Fill the Hydro addendum. Returns None for projects that have no Hydro."""
    if project not in HYDRO_PROJECTS:
        return None
    template = os.path.join(HYDRO_DIR, f"{project} - Hydro.pdf")
    if not os.path.exists(template):
        raise FormError(f"no Hydro template for project {project}")
    if not (lease_number and address and tenant_name):
        raise FormError("Hydro needs the lease number, address and tenant name")

    # French and English halves carry the same values.
    values = {
        "fr_lease_number": lease_number, "en_lease_number": lease_number,
        "fr_address": address,           "en_address": address,
        "fr_tenant_name": tenant_name,   "en_tenant_name": tenant_name,
        "fr_date": date,                 "en_date": date,
    }
    out = _write(template, values, os.path.join(out_dir, "Hydro.pdf"))

    # The supplied masters had been reused between tenancies; guard against a
    # previous tenant's details surviving into a new lease.
    got = PdfReader(out).get_fields() or {}
    stale = [k for k, v in got.items()
             if v.get("/V") and str(v["/V"]) != str(values.get(k, ""))]
    if stale:
        raise FormError(f"unexpected leftover values in {out}: {sorted(stale)}")
    return out
