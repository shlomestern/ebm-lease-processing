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
ROW = 32          # gap between labelled rows
BLOCK_GAP = 74    # gap between the French and English halves
HERE = os.path.dirname(__file__)
LOGO = os.path.join(HERE, "..", "logo_0.png")
HQ_LOGO = os.path.join(HERE, "..", "hydroquebec-logo.png")

# Projects whose tenants sign the Hydro addendum, and the buildings it covers.
# Excludes projects where hydro is included in the rent (19, 22, 26, 34, 44,
# 46, 48) and, for 24, the 7775 building.
BUILDINGS = {
    "13": ["9379 Lasalle", "9399 Lasalle", "9419 Lasalle", "9400 Centrale"],
    "14": ["3225 Langelier", "3245 Langelier", "3265 Langelier", "3285 Langelier",
           "3195 Parkville", "3215 Parkville"],
    "17": ["585 77e Avenue", "595 77e Avenue", "615 77e Avenue", "665 77e Avenue",
           "725 77e Avenue", "755 77e Avenue"],
    "24": ["7725 Trahan"],   # 7775 has hydro included in the rent
    "28": ["189 Bishop-Power", "229 Bishop-Power"],
    "30": ["400 Lansdowne", "1669 Ringuet"],
    "31": ["5295 Des Erables"],
    "32": ["11666 St-Germain"],
    "33": ["5911 Parc Ave"],
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


def draw_rich(c, segments, x, y, maxw, size=9.5, leading=14):
    """Draw a paragraph whose runs mix regular and bold, wrapping across runs.

    segments is [(text, is_bold), ...]. Returns the y below the last line.
    """
    words = []                       # (word, bold)
    for text, bold in segments:
        parts = text.split(" ")
        for i, w_ in enumerate(parts):
            if w_ == "":
                continue
            words.append((w_, bold))
    line, cur = [], 0.0
    space_r = c.stringWidth(" ", "Helvetica", size)
    space_b = c.stringWidth(" ", "Helvetica-Bold", size)
    for w_, bold in words:
        font = "Helvetica-Bold" if bold else "Helvetica"
        ww = c.stringWidth(w_, font, size)
        sp = (space_b if bold else space_r) if line else 0
        if cur + sp + ww > maxw and line:
            cx = x
            for lw, lb, lsp in line:
                cx += lsp
                c.setFont("Helvetica-Bold" if lb else "Helvetica", size)
                c.drawString(cx, y, lw)
                cx += c.stringWidth(lw, "Helvetica-Bold" if lb else "Helvetica", size)
            y -= leading
            line, cur = [(w_, bold, 0)], ww
        else:
            line.append((w_, bold, sp)); cur += sp + ww
    if line:
        cx = x
        for lw, lb, lsp in line:
            cx += lsp
            c.setFont("Helvetica-Bold" if lb else "Helvetica", size)
            c.drawString(cx, y, lw)
            cx += c.stringWidth(lw, "Helvetica-Bold" if lb else "Helvetica", size)
        y -= leading
    return y


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
        # The paragraph is regular weight except for the emphasised clause,
        # which is bold on the originals.
        segments = {
            "FR": [
                ("Le nouveau locataire ", False),
                ("a été expliqué et a compris qu'il est de sa responsabilité "
                 "d'aviser Hydro Québec", True),
                (f" de leur nouvelle adresse et date d'aménagement, {UP} n'est pas "
                 "responsable de l'Hydro du locataire.", False),
            ],
            "EN": [
                ("The new tenant was explained and understood that it is his or her ", False),
                ("responsibility to advise Hydro Quebec", True),
                (f" of their new address and moving date, {UP} is not responsible "
                 "for the tenant Hydro.", False),
            ],
        }[lang]
        p = lang.lower()
        c.setFont("Helvetica-Bold", 10)
        c.drawString(L, y, t["date"]);  field(f"{p}_date", L + 62, y, 160, h=16); y -= ROW
        c.drawString(L, y, t["num"])
        field(f"{p}_lease_number", L + c.stringWidth(t["num"], "Helvetica-Bold", 10) + 8, y, 200, h=16); y -= ROW
        c.drawString(L, y, t["addr"])
        field(f"{p}_address", L + c.stringWidth(t["addr"], "Helvetica-Bold", 10) + 8, y, 310, h=16); y -= ROW
        c.drawString(L, y, t["who"])
        field(f"{p}_tenant_name", L + c.stringWidth(t["who"], "Helvetica-Bold", 10) + 8, y, 290, h=16); y -= ROW + 6
        # body paragraph — regular, with the emphasised clause in bold
        y = draw_rich(c, segments, L, y, R - L, size=9.5, leading=14)
        y -= 22
        c.setFont("Helvetica-Bold", 10)
        c.drawString(L, y, t["sig"])
        sx = L + c.stringWidth(t["sig"], "Helvetica-Bold", 10) + 8
        c.line(sx, y - 2, sx + 260, y - 2)
        y -= BLOCK_GAP

    block("FR")
    block("EN")

    # Sign-off sits near the foot of the page so the sheet reads as a full
    # letter rather than trailing off with a blank lower half.
    c.setFont("Helvetica-Bold", 10)
    c.drawString(L, max(y, 96), "The Administration")

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
