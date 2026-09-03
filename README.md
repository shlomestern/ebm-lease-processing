# EBM lease processing

Automation for Empire Building Management's lease pipeline: a lease request
arrives by email, and within minutes the sender is acknowledged and Claude
begins drafting the lease in CORPIQ (ProprioLocation).

The authoritative description of *how a lease is drafted* lives in Shlome's
Claude memory (`/areas/leases.md`) and the `ebm-lease-processing` skill. This
repository holds only the parts that have to exist as files.

## The pipeline

```
lease request email  ->  Gmail bridge (Apps Script, every 60s)
                           |- sends the acknowledgment reply
                           `- POSTs the routine's /fire endpoint
                     ->  Claude session starts within ~1-2 min
                           |- drafts the lease in CORPIQ
                           |- attaches the EFT and Hydro annexes
                           `- sends it for verification in CORPIQ
                     ->  tenant notified (lease to sign + send a void cheque)
                     ->  signatures  +  void cheque received
                     ->  lease concluded, documents filed to the team
```

Everything signs inside CORPIQ. Docusign and Adobe are not used.

## Layout

| Path | What it is |
|---|---|
| `forms/eft/` | 46 EFT forms — one per project, English and French |
| `forms/hydro/` | 15 Hydro-Québec addenda — only these projects have one |
| `tools/companies.py` | project number -> company legal name |
| `tools/rebuild.py` | regenerates every EFT form |
| `tools/gmail-lease-bridge.gs` | the Gmail Apps Script bridge |

## Forms

### EFT (all 23 projects)

Rebuilt from scratch in `tools/rebuild.py`. The original masters carried a
company name baked into the page content underneath the company dropdown
("Le Prestigieux Pierrefonds" in the English one, "SEIGNEURIE LASALLE" in the
French), so a single form could name three different companies at once. These
have no dropdown: the company appears as static text and is correct for the
project.

Filled by the automation: `tenant_name`, `building`, `unit`, `tel`,
`rent_amount`, `start_date`, `first_amount`, `date`.

Left blank for the tenant: `account_1`-`account_10`, `transit_1`-`transit_5`,
`institution_1`-`institution_3`, `institution_name`, the signature and its date.
The tenant cannot enter banking details in CORPIQ, which is why the form asks
for a void cheque by email.

To regenerate after changing a company name or the office address:

```bash
python3 -m venv .venv && .venv/bin/pip install pypdf reportlab pillow
.venv/bin/python tools/rebuild.py     # writes eft-rebuilt/
```

### Hydro (15 projects: 13, 14, 17, 22, 24, 28, 30, 31, 32, 33, 34, 38, 40, 42, 50)

A bilingual addendum in which the tenant acknowledges that notifying
Hydro-Québec is their own responsibility. French and English halves hold the
same three values, so both must be written:

| French | English | Value |
|---|---|---|
| `Text9` | `Text12` | CORPIQ lease number |
| `Text10` | `Text13` | apartment + building address |
| `Text11` | `Text14` | tenant name |

The copies here have been stripped of the previous tenants' data. **Clear every
field before writing** — the originals also carried stale signature dates on
projects 34 and 38 — and verify no old value survives before attaching, so a
new tenant never receives a form naming someone else.

## Known gaps

- **Project 45 (Le 7040 Inc.)** is not in use. Its EFT exists for when it is.
- The office address on the EFT header came from a newer version of the form
  than the masters used here. If any company uses a different address, change
  `OFFICE_ADDRESS` in `tools/rebuild.py`.
- Project 26 is **Seigneurie Lasalle Inc.**; the projects workbook spells it
  "Seigneure".

## The Gmail bridge

`tools/gmail-lease-bridge.gs` runs in Apps Script on the team mailbox, every
minute. It classifies new mail, sends the acknowledgment itself (so the reply
never waits on Claude), labels the thread, and fires the routine's API trigger.

Configuration lives in Script Properties, never in the file: `FIRE_URL` and
`FIRE_TOKEN`.

Four guards keep it from running away — on 2026-09-01 an earlier version
answered its own replies and sent ~93 duplicates:

1. its own acknowledgment is always recognised, with no subject carve-out
2. it never replies to a message from itself
3. it replies to the requester's message, not the thread's last message
4. a hard ceiling of `MAX_ACKS_PER_DAY` (12) emails per day
