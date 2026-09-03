"""
Rebuild the Hydro-Québec addendum, one file per project, styled like the EFT
form (logo left, company name centred in plain black, addresses beneath).

Why a rebuild: the supplied masters were reused between tenancies and still
carried the previous tenant's name, lease number and — on projects 34 and 38 —
their signature dates. Several also render the company name as an image, in a
decorative font, with typos ("parkvew realties", "simo realities", and
"responsivity" for "responsibility"). These are generated from the projects
workbook, so every company name is the legal one and every form is empty.

Bilingual: the French and English halves hold the same three values, so the
automation writes each of them twice.
"""
import os, sys, re
sys.path.insert(0, os.path.dirname(__file__))
from companies import COMPANIES
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.colors import HexColor, black
from reportlab.lib.utils import ImageReader

W, H = LETTER
FIELD_BG = HexColor("#DCE3F5")
HERE = os.path.dirname(__file__)
LOGO = os.path.join(HERE, "..", "logo_0.png")
HQ_LOGO = os.path.join(HERE, "..", "hydroquebec-logo.png")

# Projects that have a Hydro addendum, and their buildings (from the workbook).
BUILDINGS = {
    "13": ["9379 Lasalle", "9399 Lasalle", "9419 Lasalle", "9400 Centrale"],
    "14": ["3225 Langelier", "3245 Langelier", "3265 Langelier", "3285 Langelier",
           "3195 Parkville", "3215 Parkville"],
    "17": ["585 77e Avenue", "595 77e Avenue", "615 77e Avenue", "665 77e Avenue",
           "725 77e Avenue", "755 77e Avenue"],
    "22": ["10301 Gouin Ouest", "10309 Gouin Ouest"],
    "24": ["7725 Trahan", "7775 Trahan"],
    "28": ["189 Bishop-Power", "229 Bishop-Power"],
    "30": ["400 Lansdowne", "1669 Ringuet"],
    "31": ["5295 Des Erables"],
    "32": ["11666 St-Germain"],
    "33": ["5911 Parc Ave"],
    "34": ["17000 Pierrefonds", "17100 Pierrefonds", "17017 Emile-Nelligan",
           "17111 Emile-Nelligan", "17115 Emile-Nelligan", "17125 Emile-Nelligan",
           "4900 Louis-Frechette", "4905 Louis-Frechette"],
    "38": ["5587-5603 de l'Esplanade"],
    "40": ["11055 Touchette", "11065 Touchette", "11075 Touchette"],
    "42": ["12200 Pierrefonds", "12210 Pierrefonds"],
    "50": ["1015 Rue Chomedey", "1025 Rue Chomedey", "1035 Rue Chomedey",
           "3290 Rue Monod", "3300 Rue Monod"],
}


def group_addresses(items):
    """'3225 Langelier', '3245 Langelier' -> '3225 & 3245 Langelier'."""
    streets, order = {}, []
    for it in items:
        m = re.match(r"^([\d\-]+)\s+(.*)$", it)
        if not m:
            streets.setdefault(it, []); order.append(it) if it not in order else None
            continue
        num, street = m.groups()
        if street not in streets:
            streets[street] = []; order.append(street)
        streets[street].append(num)
    out = []
    for street in order:
        nums = streets[street]
        if not nums:
            out.append(street)
        elif len(nums) == 1:
            out.append(f"{nums[0]} {street}")
        else:
            out.append(f"{', '.join(nums[:-1])} & {nums[-1]} {street}")
    return out


def build(path, project, company):
    c = canvas.Canvas(path, pagesize=LETTER)
    c.setTitle(f"Hydro-Québec addendum - {company}")
    form = c.acroForm
    L, R = 58, W - 58
    y = H - 55
    UP = company.upper()

    def field(name, x, yy, w, h=14):
        form.textfield(name=name, x=x, y=yy - 3, width=w, height=h, borderWidth=0,
                       fillColor=FIELD_BG, textColor=black, fontSize=9,
                       forceBorder=False)

    # ---- header: same shape as the EFT form ----
    c.drawImage(ImageReader(LOGO), L, y - 62, width=78, height=72, mask="auto")
    cx = W / 2 + 30
    c.setFillColor(black)
    c.setFont("Helvetica", 19)
    c.drawCentredString(cx, y - 22, company)
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(HexColor("#1F3864"))
    ay = y - 40
    for line in group_addresses(BUILDINGS[project]):
        c.drawCentredString(cx, ay, line)
        ay -= 11
    c.setFillColor(black)
    # Hydro-Québec mark sits clear below the EBM logo, as on the originals.
    hq_top = y - 72                      # EBM logo bottom edge is at y-62
    c.drawImage(ImageReader(HQ_LOGO), L, hq_top - 44, width=66, height=44, mask="auto")
    top_of_rule = min(ay - 10, hq_top - 54)
    c.setLineWidth(1)
    c.line(L, top_of_rule, R, top_of_rule)
    y = top_of_rule - 28

    def block(lang):
        nonlocal y
        t = {
            "FR": dict(date="Date :", num="Addenda au bail Numéros #", addr="Adresse",
                       who="Nom du/des locataires :", sig="Signature:",
                       body=("Le nouveau locataire a été expliqué et a compris qu'il est de sa "
                             "responsabilité d'aviser Hydro Québec de leur nouvelle adresse et date "
                             f"d'aménagement, {UP} n'est pas responsable de l'Hydro du locataire.")),
            "EN": dict(date="Date:", num="Addendum to lease Numbers #", addr="Address",
                       who="Tenant name:", sig="Signature:",
                       body=("The new tenant was explained and understood that it is his or her "
                             "responsibility to advise Hydro Quebec of their new address and moving "
                             f"date, {UP} is not responsible for the tenant Hydro.")),
        }[lang]
        p = lang.lower()
        c.setFont("Helvetica-Bold", 9.5)
        c.drawString(L, y, t["date"]);  field(f"{p}_date", L + 60, y, 150); y -= 22
        c.drawString(L, y, t["num"])
        field(f"{p}_lease_number", L + c.stringWidth(t["num"], "Helvetica-Bold", 9.5) + 8, y, 190); y -= 22
        c.drawString(L, y, t["addr"])
        field(f"{p}_address", L + c.stringWidth(t["addr"], "Helvetica-Bold", 9.5) + 8, y, 300); y -= 22
        c.drawString(L, y, t["who"])
        field(f"{p}_tenant_name", L + c.stringWidth(t["who"], "Helvetica-Bold", 9.5) + 8, y, 280); y -= 26
        # body paragraph
        c.setFont("Helvetica", 9)
        words, line = t["body"].split(), ""
        for w_ in words:
            trial = (line + " " + w_).strip()
            if c.stringWidth(trial, "Helvetica", 9) <= (R - L):
                line = trial
            else:
                c.drawString(L, y, line); y -= 12; line = w_
        if line:
            c.drawString(L, y, line); y -= 12
        y -= 14
        c.setFont("Helvetica-Bold", 9.5)
        c.drawString(L, y, t["sig"])
        sx = L + c.stringWidth(t["sig"], "Helvetica-Bold", 9.5) + 8
        c.line(sx, y - 2, sx + 250, y - 2)
        y -= 34

    block("FR")
    block("EN")

    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(L, y, "The Administration")

    c.showPage()
    c.save()


if __name__ == "__main__":
    out = "hydro-rebuilt"
    os.makedirs(out, exist_ok=True)
    n = 0
    for project in sorted(BUILDINGS, key=int):
        build(f"{out}/{project} - Hydro.pdf", project, COMPANIES[project])
        n += 1
    print(f"built {n} Hydro forms")
