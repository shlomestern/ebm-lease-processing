"""
Rebuild the EFT form cleanly, one file per project per language.

Why a rebuild: the original masters carry a hard-coded company name in the page
content ("Le Prestigieux Pierrefonds" in EN, "SEIGNEURIE LASALLE" in FR) hidden
underneath the company dropdown widget. Editing the dropdown left that buried
text in place, so a form could show three different companies at once. These
templates have no dropdown and no buried text: the company appears once, as
static text, and it is correct for the project.

Legal wording is reproduced verbatim from the originals.
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from companies import COMPANIES
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.utils import ImageReader

W, H = LETTER
BLUE = HexColor("#1F3F94")
FIELD_BG = HexColor("#DCE3F5")
LOGO = os.path.join(os.path.dirname(__file__), "..", "logo_0.png")

# Management office address shown under the company name. Taken from the header
# Shlome supplied; it was NOT present in the two master PDFs, so if any company
# uses a different address this is the one line to change.
OFFICE_ADDRESS = [
    "6750 Ave. Du Parc Suite 220",
    "Montréal, QC H3N 1W7",
    "(514) 278-4540",
]

TXT = {
    "EN": {
        "title": "Electronic Funds Transfer",
        "name": "*Name:", "building": "*Building:", "unit": "*Unit #:", "tel": "Tel:",
        "bank": "Bank Account Information",
        "acct": "*Account Number:", "transit": "*Branch Transit Number:",
        "inst": "*Financial Institution:", "instname": "*Financial Institution Name:",
        "auth": ("I, the undersigned hereby authorize %s and the financial institution "
                 "designated to begin deductions for my monthly rent."),
        "reg1": "Regular monthly payments for the full amount of my rent payable, $",
        "reg2": ", will be withdrawn monthly from my specified account starting on",
        "reg3": ", for the full term of my lease, and will be increased in accordance with my signed renewal notices.",
        "first": "First amount to withdraw if different than above (minus any initial deposit)  $",
        "date": "Date",
        "legal": ("This authority is to remain in effect until the landlord has received written notification from me "
                  "of its change or termination. This notification must be received at least ten (10) business days "
                  "before the next debit is scheduled. I may obtain a sample cancellation form or more information on "
                  "my right to cancel a PAD Agreement at my financial institution or by visiting www.cdnpay.ca."),
        "sig": "*Signature of Account Holder:", "sigdate": "Date",
        "void": "*please attach a void cheque",
    },
    "FR": {
        "title": "Transfert Électronique de Fonds",
        "name": "*Nom:", "building": "*Édifice:", "unit": "*Appartement #:", "tel": "Tél:",
        "bank": "Information bancaire",
        "acct": "*Numéro de compte:", "transit": "*Numéro de succursale:",
        "inst": "*Institution financière:", "instname": "*Nom de l'institution financière :",
        "auth": ("Je, soussigné, autorise par la présente « %s » et l'institution financière "
                 "désignée pour commencer les retraits pour mon loyer mensuel. Des paiements mensuels réguliers "
                 "pour le montant total de"),
        "reg1": "mon loyer payable, ",
        "reg2": "$, seront retirés de mon compte spécifié, débutant ",
        "reg3": " pour toute la durée de mon bail et seront augmentés conformément à mes avis de renouvellement signés.",
        "first": "Premier retrait si différent du montant ci-haut (soustraire dépôt initial)  ",
        "date": "Date",
        "legal": ("Ce pouvoir restera en vigueur jusqu'à ce que le locateur ait reçu de ma part une notification "
                  "écrite d'un changement ou d'une résiliation. Cette notification doit être reçue au moins dix (10) "
                  "jours ouvrables avant le prochain débit. Je peux obtenir un exemple de formulaire d'annulation ou "
                  "plus d'informations sur mon droit d'annuler un accord de DPA auprès de mon institution financière "
                  "ou en visitant le site www.cdnpay.ca."),
        "sig": "*Signature:", "sigdate": "Date:",
        "void": "*veuillez fournir un spécimen de chèque",
    },
}


def wrap(c, text, font, size, maxw):
    c.setFont(font, size)
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if c.stringWidth(t, font, size) <= maxw:
            cur = t
        else:
            lines.append(cur); cur = w_
    if cur:
        lines.append(cur)
    return lines


def build(path, lang, company):
    t = TXT[lang]
    c = canvas.Canvas(path, pagesize=LETTER)
    c.setTitle(f"Electronic Funds Transfer - {company}")
    form = c.acroForm
    L, R = 58, W - 58
    y = H - 55

    # ---- header: logo left, company name centred, office address beneath ----
    c.drawImage(ImageReader(LOGO), L, y - 62, width=78, height=72, mask="auto")
    cx = W / 2 + 30          # centred over the space to the right of the logo
    c.setFillColor(black)
    c.setFont("Helvetica", 19)
    c.drawCentredString(cx, y - 22, company)
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(HexColor("#1F3864"))
    ay = y - 40
    for line in OFFICE_ADDRESS:
        c.drawCentredString(cx, ay, line)
        ay -= 11
    c.setFillColor(black)
    c.setLineWidth(1)
    c.line(L, y - 82, R, y - 82)
    y -= 106

    # ---- title ----
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(W / 2, y, t["title"])
    y -= 28

    # ---- tenant block ----
    def field(name, x, yy, w, h=14, maxlen=None):
        form.textfield(name=name, x=x, y=yy - 3, width=w, height=h,
                       borderWidth=0, fillColor=FIELD_BG, textColor=black,
                       fontSize=9, maxlen=maxlen, forceBorder=False)

    c.setFont("Helvetica-Bold", 9)
    for lbl, key in ((t["name"], "tenant_name"), (t["building"], "building"),
                     (t["unit"], "unit"), (t["tel"], "tel")):
        c.setFont("Helvetica-Bold", 9)
        c.drawString(L + 55, y, lbl)
        field(key, L + 175, y, 210)
        y -= 21

    # ---- bank block ----
    y -= 6
    c.setFont("Helvetica-Bold", 10)
    c.drawString(L + 55, y, t["bank"])
    c.line(L + 55, y - 2, L + 55 + c.stringWidth(t["bank"], "Helvetica-Bold", 10), y - 2)
    y -= 22

    def boxes(prefix, n, xstart, yy, bw=21, bh=16):
        for i in range(n):
            form.textfield(name=f"{prefix}_{i+1}", x=xstart + i * (bw + 2), y=yy - 3,
                           width=bw, height=bh, borderWidth=0.6, borderColor=black,
                           fillColor=FIELD_BG, fontSize=9, maxlen=1, forceBorder=True)

    c.setFont("Helvetica-Bold", 9)
    c.drawString(L + 65, y, t["acct"]);     boxes("account", 10, L + 285, y); y -= 24
    c.drawString(L + 65, y, t["transit"]);  boxes("transit", 5, L + 285, y);  y -= 24
    c.drawString(L + 65, y, t["inst"]);     boxes("institution", 3, L + 285, y); y -= 24
    c.drawString(L + 75, y, t["instname"])
    field("institution_name", L + 75 + c.stringWidth(t["instname"], "Helvetica-Bold", 9) + 6, y, 200)
    y -= 30

    # ---- authorization paragraph (company is STATIC text here) ----
    c.setFillColor(black)
    for line in wrap(c, t["auth"] % company, "Helvetica-Bold", 9, R - L):
        c.setFont("Helvetica-Bold", 9)
        c.drawString(L, y, line); y -= 12
    y -= 4

    # ---- rent + start date ----
    # Each inline field gets its own line so nothing can overflow the right
    # margin, whatever the label length is in either language.
    c.setFont("Helvetica-Bold", 9)
    c.drawString(L, y, t["reg1"])
    field("rent_amount", L + c.stringWidth(t["reg1"], "Helvetica-Bold", 9) + 4, y, 100)
    y -= 18
    lead = t["reg2"].lstrip(", ")
    c.setFont("Helvetica-Bold", 9)
    c.drawString(L, y, lead)
    field("start_date", L + c.stringWidth(lead, "Helvetica-Bold", 9) + 6, y, 130)
    y -= 18
    for line in wrap(c, t["reg3"].lstrip(", "), "Helvetica-Bold", 9, R - L):
        c.setFont("Helvetica-Bold", 9); c.drawString(L, y, line); y -= 12
    y -= 8

    c.setFont("Helvetica-Bold", 9)
    c.drawString(L, y, t["first"])
    field("first_amount", L + c.stringWidth(t["first"], "Helvetica-Bold", 9) + 4, y, 100)
    y -= 24
    c.drawString(L, y, t["date"])
    field("date", L + 40, y, 150)
    y -= 28

    # ---- legal paragraph ----
    for line in wrap(c, t["legal"], "Helvetica-Bold", 8.5, R - L):
        c.setFont("Helvetica-Bold", 8.5); c.drawString(L, y, line); y -= 11
    y -= 26

    # ---- signature ----
    c.setFont("Helvetica-Bold", 9)
    c.drawString(L, y, t["sig"])
    sx = L + c.stringWidth(t["sig"], "Helvetica-Bold", 9) + 6
    c.line(sx, y - 2, sx + 215, y - 2)
    c.drawString(sx + 228, y, t["sigdate"])
    field("signature_date", sx + 228 + c.stringWidth(t["sigdate"], "Helvetica-Bold", 9) + 5, y, 95)
    y -= 30

    # ---- void cheque box ----
    c.setLineWidth(1)
    c.rect(L, y - 6, R - L, 22, stroke=1, fill=0)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(W / 2, y + 2, t["void"])

    c.showPage()
    c.save()


if __name__ == "__main__":
    out = "eft-rebuilt"
    os.makedirs(out, exist_ok=True)
    made = 0
    for proj, company in COMPANIES.items():
        for lang in ("EN", "FR"):
            build(f"{out}/{proj} - EFT - {lang}.pdf", lang, company)
            made += 1
    print(f"built {made} files")
