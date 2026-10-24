"""`docs` families, part A: invoice, receipt, order confirmation, shipping notice, bank
statement, timesheet, flight itinerary, hotel booking.

Each family draws structured values first, renders the text from them, and registers field
candidates whose gold comes from the structured values (never parsed back from the text).
"""

from __future__ import annotations

import datetime as dt
import random

from .docs_kit import (MON, MONEY_STYLES, NOYEAR_STYLES, TIME_STYLES, WEEKDAYS, YEAR_STYLES, Doc,
                       code, fdate, fdur_hm, fmoney, fnum, fpct, ftime, pct_of, rand_date,
                       rand_minutes, slug, yearless_ok)

DAY = dt.timedelta(days=1)

SERVICE_LINES = (
    "Consulting hours", "Website maintenance retainer", "Data migration", "On-site support visit",
    "Software licence renewal", "Training workshop (half day)", "Security review",
    "Report design and build", "Project management", "Cloud hosting (monthly)",
)
SUPPLY_LINES = (
    "Hex bolts M8x40 (box of 100)", "Bearing 6204-2RS", "Hydraulic hose 3/8in x 2m",
    "Safety gloves, size L (pair)", "Cable ties 300mm (pack of 100)", "Pallet wrap 500mm roll",
    "Air filter 20x25x1", "Drive belt B42", "Grease cartridge 400g", "A4 copy paper (box of 5 reams)",
    "Toner cartridge TN-450", "Label tape 12mm", "Shelf bracket 300mm", "Corrugated boxes 40x30x30 (25)",
)
GROCERY = (
    "Oat milk 1L", "Sourdough loaf", "Free-range eggs x12", "Bananas 1.2kg", "Cheddar 400g",
    "Coffee beans 500g", "Greek yogurt 500g", "Baby spinach 200g", "Olive oil 750ml",
    "Penne pasta 500g", "Vine tomatoes 6pk", "Dark chocolate 100g", "Basmati rice 1kg",
    "Apple juice 1L", "Butter 250g", "Granola 750g",
)
HARDWARE = (
    "Wood screws 4x40mm", "Paint roller 9in", "Masking tape 24mm", "Extension cord 5m",
    "LED bulb E27 9W", "Sandpaper assorted", "Silicone sealant clear", "Drill bit set 8pc",
    "Wall plugs 100pk", "Cable ties 200mm", "Work gloves L", "Duct tape 48mm",
)
PHARMACY = (
    "Vitamin D 1000IU 90ct", "Hand cream 75ml", "Sunscreen SPF50 200ml", "Toothpaste 100ml",
    "Bandages assorted 40", "Lip balm", "Allergy relief 30ct", "Shampoo 400ml", "Cotton pads 100ct",
    "Throat lozenges 24",
)
STORE_KINDS = (("Market", GROCERY, (89, 1299)), ("Grocers", GROCERY, (89, 1299)),
               ("Hardware", HARDWARE, (199, 4999)), ("Home & Garden", HARDWARE, (199, 4999)),
               ("Pharmacy", PHARMACY, (249, 1899)))
RETAIL = (
    "Wireless earbuds", "Yoga mat 6mm", "Insulated water bottle 750ml", "LED desk lamp",
    "Travel backpack 28L", "Clear phone case", "Portable speaker", "Running socks 3-pack",
    "Cast iron skillet 10in", "Wool throw blanket", "Ceramic mug set (4)", "Bamboo cutting board",
    "Hiking poles (pair)", "Linen tea towels (2)", "French press 1L",
)


def _money(r: random.Random, cur: str = "USD"):
    style = r.choice(MONEY_STYLES)
    return lambda c: fmoney(c, style, cur)


def _dates(r: random.Random, dates, ref: dt.date | None, p_noyear: float = 0.5,
           weekday: bool = True):
    """A date formatter for one document. Yearless styles only when `ref` makes them safe;
    returns (formatter, used_yearless). `weekday=False` drops styles that print the weekday."""
    if ref is not None and yearless_ok(dates, ref) and r.random() < p_noyear:
        style = r.choice([s for s in NOYEAR_STYLES if weekday or not s.startswith("wd")])
        return (lambda d: fdate(d, style)), True
    style = r.choice([s for s in YEAR_STYLES if weekday or not s.startswith("wd")])
    return (lambda d: fdate(d, style)), False


def _first(name: str) -> str:
    return name.split()[0]


def _email(name: str, company_short: str) -> str:
    return f"{slug(_first(name))}.{slug(name.split()[-1])}@{slug(company_short)}.example"


def _pad(rows, widths, aligns):
    out = []
    for row in rows:
        cells = []
        for cell, w, a in zip(row, widths, aligns):
            cells.append(cell.rjust(w) if a == "r" else cell.ljust(w))
        out.append("  ".join(cells).rstrip())
    return out


# ================================================================ invoice

def invoice(r: random.Random, layout: str) -> Doc:
    doc = Doc(r, "invoice", layout)
    cur = r.choice(("USD", "USD", "USD", "EUR", "GBP"))
    M = _money(r, cur)
    services = r.random() < 0.4
    seller, seller_short = doc.company(("Consulting", "Digital", "Analytics", "Studio")
                                       if services else
                                       ("Supply", "Components", "Industrial", "Distribution"))
    buyer, buyer_short = doc.company(("Logistics", "Foods", "Retail", "Health", "Hospitality"))
    contact, buyer_contact = doc.person(), doc.person()
    issue = rand_date(r)
    order = issue - DAY * r.randint(3, 20)
    deliv = order + DAY * r.randint(1, (issue - order).days)
    D, _ = _dates(r, [issue], None)
    net = r.choice((14, 15, 30, 30, 45, 60))
    due = issue + DAY * net
    inv_no = r.choice((code(r, "INV-####"), f"INV-{issue.year}-{code(r, '####')}",
                       f"{seller_short[:2].upper()}-{code(r, '#####')}"))
    pool = SERVICE_LINES if services else SUPPLY_LINES
    lines = []
    for desc in r.sample(pool, r.randint(2, 5)):
        if services:
            qty = r.choice((1, 1, 2, 4, 6, 8, 10, 12, 16))
            unit = r.randint(15, 39) * 500 if qty > 1 else r.randint(50, 960) * 500
        else:
            qty = r.randint(1, 24)
            unit = r.randint(250, 48000)
        lines.append((desc, qty, unit, qty * unit))
    subtotal = sum(x[3] for x in lines)
    vat = cur != "USD"
    bp = (2000 if cur == "GBP" else r.choice((1900, 2000, 2100))) if vat else \
        r.choice((500, 600, 700, 825, 875, 1000))
    tax_label = "VAT" if vat else "Sales tax"
    tax = pct_of(subtotal, bp)
    extra_label = None if services else r.choice(("Shipping", "Freight", "Delivery"))
    extra = 0 if services else r.choice((0, 1500, 2500, 3900, 4999, 7500, 12000))
    total = subtotal + tax + extra
    has_po = r.random() < 0.5
    po = r.choice((code(r, "PO-#####"), code(r, "#######"), f"PO{issue.year}-{code(r, '###')}"))
    po_line = (f"Customer PO: {po}" if has_po else
               r.choice(("Customer PO: to follow", "Customer PO: pending", "")))
    late = r.choice((100, 150, 200)) if r.random() < 0.35 else None
    late_line = f"Late payments are charged {fpct(late)} per month." if late else ""
    phone = code(r, "555-01##") if r.random() < 0.4 else None
    vat_no = code(r, "@@ ### #### ##") if (vat and r.random() < 0.5) else None
    has_deliv = not services and r.random() < 0.35
    print_due = r.random() < (0.6 if layout == "kv" else 0.35)
    print_total = layout != "email" or r.random() < 0.5
    tax_text = f"{tax_label} ({fpct(bp)})"

    if layout == "email":
        hdr = [f"From: {contact} <{_email(contact, seller_short)}>",
               f"To: {buyer_contact}, {buyer} <accounts@{slug(buyer_short)}.example>",
               f"Subject: Invoice {inv_no} from {seller}",
               f"Date: {D(issue)}", "",
               f"Hi {_first(buyer_contact)},", "",
               r.choice(("Please find attached", "Attached is", "Here is")) +
               f" invoice {inv_no}, dated {D(issue)}, for "
               + ("the work below." if services else "your recent order.") + "", ""]
        body = [f"  - {d}: {q} x {M(u)} = {M(t)}" for d, q, u, t in lines]
        sums = f"Subtotal {M(subtotal)}, {tax_text} {M(tax)}"
        if extra_label:
            sums += f", {extra_label.lower()} {M(extra)}"
        sums += "." + (f" The total due is {M(total)}." if print_total else "")
        terms = f"Payment terms are net {net} days" + (f", so payment is due by {D(due)}." if print_due else ".")
        tail = [x for x in (po_line.replace("Customer PO:", "Your PO reference:") if po_line else "",
                            late_line) if x]
        sign = ["", r.choice(("Kind regards,", "Thanks,", "Best regards,")), contact,
                f"Accounts Receivable, {seller}"] + ([f"Tel. {phone}"] if phone else []) + \
               ([f"VAT reg. no. {vat_no}"] if vat_no else [])
        doc.state = "\n".join(hdr + body + ["", sums, terms] + tail + sign)
    elif layout == "kv":
        head = [seller, f"{doc.street()}, {doc.city()[0]}"]
        if phone:
            head.append(f"Tel. {phone}")
        if vat_no:
            head.append(f"VAT reg. no. {vat_no}")
        kv = [("Invoice number", inv_no), ("Invoice date", D(issue))]
        if not services:
            kv.append(("Order date", D(order)))
        if has_deliv:
            kv.append(("Delivered", D(deliv)))
        kv.append(("Payment terms", f"Net {net}"))
        if print_due:
            kv.append(("Due date", D(due)))
        kv += [("Bill to", buyer), ("Attention", buyer_contact)]
        if po_line:
            k, v = po_line.split(": ", 1)
            kv.append((k, v))
        w = max(len(k) for k, _ in kv) + 2
        body = [f"{(k + ':').ljust(w)}{v}" for k, v in kv]
        dw = max(len(x[0]) for x in lines) + 2
        rows = [("#", "Description", "Qty", "Unit price", "Amount")] + [
            (str(i + 1), d, str(q), M(u), M(t)) for i, (d, q, u, t) in enumerate(lines)]
        mw = max(len(x[k]) for x in rows for k in (3, 4))
        table = _pad(rows, (2, dw, 4, mw, mw), "llrrr")
        sums = [("Subtotal", M(subtotal)), (tax_text, M(tax))]
        if extra_label:
            sums.append((extra_label, M(extra)))
        sums.append(("Total due", M(total)))
        lead = 2 + dw + 4 + 4
        tot = [f"{' ' * lead}{k.ljust(18)}  {v.rjust(13)}" for k, v in sums]
        foot = [x for x in (late_line, f"Questions about this invoice: {contact}, "
                            f"{_email(contact, seller_short)}") if x]
        doc.state = "\n".join(head + ["", "INVOICE", ""] + body + [""] + table + tot + [""] + foot)
    else:  # markdown-style table
        top = [f"{seller} | Invoice {inv_no}", f"Bill to: {buyer} (attn. {buyer_contact})",
               f"Date: {D(issue)} | Terms: Net {net}" + (f" | Due: {D(due)}" if print_due else "")]
        if po_line:
            top.append(po_line)
        if phone:
            top.append(f"Contact: {contact}, tel. {phone}")
        else:
            top.append(f"Contact: {contact}")
        rows = ["", f"| Line | Description | Qty | Unit ({cur}) | Total ({cur}) |", "|---|---|---|---|---|"]
        rows += [f"| {i + 1} | {d} | {q} | {fnum(u)} | {fnum(t)} |" for i, (d, q, u, t) in enumerate(lines)]
        rows.append(f"| | Subtotal | | | {fnum(subtotal)} |")
        rows.append(f"| | {tax_text} | | | {fnum(tax)} |")
        if extra_label:
            rows.append(f"| | {extra_label} | | | {fnum(extra)} |")
        rows.append(f"| | Amount due | | | {fnum(total)} |")
        foot = [""] + [x for x in (late_line, f"VAT reg. no. {vat_no}" if vat_no else "") if x]
        doc.state = "\n".join(top + rows + foot + ["Thank you for your business."])

    doc.text("invoice_number", inv_no, w=2)
    doc.text("seller_name", seller, alts=[seller_short], instr="Company that issued the invoice")
    doc.text("customer_name", buyer, alts=[buyer_short], instr="Company being billed")
    doc.text("billing_contact", contact, instr="Person at the seller to contact about the invoice")
    doc.date("invoice_date", issue, instr="Issue date of the invoice")
    doc.date("due_date", due, w=2, instr="Date payment is due (the invoice date plus the net "
             "payment days, if no due date is printed)")
    doc.duration("payment_terms", net, "days", integer=True, instr="Net payment term")
    doc.money("subtotal", subtotal, cur, instr="Sum of the line items before tax"
              + (" and shipping" if extra_label else ""))
    doc.money("tax_amount", tax, cur, instr=f"{tax_label} amount")
    if extra_label:
        doc.money("shipping_amount", extra, cur, instr=f"{extra_label} charge")
    doc.money("total_due", total, cur, w=2.5, instr="Total amount due: subtotal plus tax"
              + (f" plus {extra_label.lower()}" if extra_label else ""))
    doc.items("line_item_descriptions", [x[0] for x in lines], "text",
              instr="Description of each line item, in invoice order")
    doc.money_items("line_amounts", [x[3] for x in lines], cur,
                    instr="Amount of each line item (quantity times unit price), in invoice order")
    doc.number("line_item_count", len(lines), integer=True, instr="Number of line items")
    doc.text("po_number", po if has_po else None, w=1.5, instr="Customer purchase order number")
    doc.number("late_fee_percent", late / 100 if late else None,
               instr="Late payment charge, in percent per month")
    doc.text("contact_phone", phone, instr="Phone number of the billing contact")
    doc.text("vat_number", vat_no, instr="Seller's VAT registration number")
    if not services:
        doc.date("delivery_date", deliv if has_deliv else None,
                 instr="Date the goods were delivered")
    doc.text("bank_iban", None, w=0.7, instr="IBAN of the account to pay into")
    doc.text("project_reference", None, instr="Customer project or cost-centre reference")
    doc.number("early_payment_discount_percent", None, instr="Discount for early payment, in percent")
    return doc


# ================================================================ retail receipt

def receipt(r: random.Random, layout: str) -> Doc:
    doc = Doc(r, "receipt", layout)
    kind, pool, (lo, hi) = r.choice(STORE_KINDS)
    stem = doc.stem()
    store = f"{stem} {kind}"
    city = doc.city()[0]
    day = rand_date(r)
    minute = rand_minutes(r, "08:00", "21:30", 1)
    thermal = layout == "thermal"
    tstyle = r.choice(("24", "12", "12l"))
    dstyle = r.choice(("dmy", "iso", "mdy")) if thermal else r.choice(YEAR_STYLES)
    D = (lambda d: fdate(d, dstyle).upper()) if thermal else (lambda d: fdate(d, dstyle))
    lines = []
    for name in r.sample(pool, r.randint(3, 7)):
        qty = r.choice((1, 1, 1, 1, 2, 2, 3))
        unit = r.randint(lo, hi)
        lines.append((name.upper() if thermal else name, qty, unit, qty * unit))
    subtotal = sum(x[3] for x in lines)
    bp = r.choice((500, 625, 700, 725, 825, 875))
    tax = pct_of(subtotal, bp)
    total = subtotal + tax
    cash = thermal and r.random() < 0.4
    tendered = change = None
    if cash:
        step = r.choice((500, 1000, 2000))
        tendered = (total // step + 1) * step
        change = tendered - total
    brand = r.choice(("VISA", "MASTERCARD", "DEBIT", "AMEX"))
    last4 = code(r, "####")
    txn = code(r, "####-##-######")
    cashier = r.choice(("Mira", "Jonas", "Leila", "Hugo", "Tamsin", "Kofi")) if r.random() < 0.5 else None
    loyalty = code(r, "4002####") if r.random() < 0.35 else None
    ret = r.choice(("date", "days", "days", "none"))
    ret_days = r.choice((14, 28, 30, 60))
    ret_by = day + DAY * ret_days if ret in ("date", "days") else None
    if ret == "date":
        ret_line = f"Return by {D(ret_by)} with this receipt."
    elif ret == "days":
        ret_line = f"Returns accepted within {ret_days} days of purchase with receipt."
    else:
        ret_line = r.choice(("Sale items are final.", "Thank you for shopping local."))
    if ret == "none" and not thermal:
        ret_line = ""
    T = ftime(minute, tstyle)
    store_phone = code(r, "555-01##")

    if thermal:
        W = 34
        out = [store.upper().center(W).rstrip(), doc.street().upper().center(W).rstrip(),
               city.upper().center(W).rstrip(), f"TEL {store_phone}".center(W).rstrip(), "",
               f"STORE {code(r, '0##')}  REG {code(r, '0#')}  TRANS {txn}", f"{D(day)}  {T}"]
        if cashier:
            out.append(f"CASHIER: {cashier.upper()}")
        out.append("-" * W)
        for name, qty, unit, amt in lines:
            out.append(name.ljust(W - 9) + fnum(amt).rjust(9))
            if qty > 1:
                out.append(f"  {qty} @ {fnum(unit)}")
        out.append("-" * W)
        out += [f"{'SUBTOTAL'.ljust(W - 9)}{fnum(subtotal).rjust(9)}",
                f"{('TAX ' + fpct(bp)).ljust(W - 9)}{fnum(tax).rjust(9)}",
                f"{'TOTAL'.ljust(W - 9)}{fnum(total).rjust(9)}"]
        if cash:
            out += [f"{'CASH'.ljust(W - 9)}{fnum(tendered).rjust(9)}",
                    f"{'CHANGE'.ljust(W - 9)}{fnum(change).rjust(9)}"]
        else:
            out += [f"{(brand + ' ****' + last4).ljust(W - 9)}{fnum(total).rjust(9)}", "APPROVED"]
        if loyalty:
            out.append(f"REWARDS ID {loyalty}")
        out += ["", ret_line.upper(), "THANK YOU!"]
        doc.state = "\n".join(out)
    else:
        M = _money(r)
        nice = {"VISA": "Visa", "MASTERCARD": "Mastercard", "DEBIT": "Debit card", "AMEX": "Amex"}[brand]
        nw = max(len(x[0]) for x in lines) + 2
        rows = _pad([("Item", "Qty", "Amount")] + [(n, str(q), M(a)) for n, q, _, a in lines],
                    (nw, 4, 11), "lrr")
        out = [f"From: {store} <receipts@{slug(stem)}.example>",
               f"Subject: Your receipt from {store}", "",
               r.choice(("Thanks for shopping at", "Thank you for visiting")) +
               f" {store}, {city}, on {D(day)} at {T}.", f"Receipt number: {txn}", ""]
        out += rows + ["", f"Subtotal: {M(subtotal)}", f"Sales tax ({fpct(bp)}): {M(tax)}",
                       f"Total charged to {nice} ending in {last4}: {M(total)}", ""]
        if cashier:
            out.append(f"You were served by {cashier}.")
        if loyalty:
            out.append(f"Rewards ID {loyalty} earned points on this purchase.")
        if ret_line:
            out.append(ret_line)
        out.append(f"Questions? Reply to this email or call the store.")
        doc.state = "\n".join(out)

    doc.text("store_name", store.upper() if thermal else store, instr="Name of the store")
    doc.date("purchase_date", day, w=1.2)
    doc.time("purchase_time", minute, w=1.5)
    doc.datetime("purchase_datetime", day, minute, instr="Date and time of the purchase")
    doc.text("transaction_number", txn, instr="Receipt or transaction number")
    doc.money("subtotal", subtotal, instr="Amount before tax")
    doc.money("tax_amount", tax)
    doc.money("total", total, w=2.5, instr="Total paid, including tax")
    doc.items("item_names", [x[0] for x in lines], "text", instr="Name of each item, as printed")
    doc.money_items("item_amounts", [x[3] for x in lines],
                    instr="Line amount of each item (quantity times unit price), in receipt order")
    doc.number("units_purchased", sum(x[1] for x in lines), integer=True, w=1.5,
               instr="Total number of units bought (the sum of the quantities)")
    if cash:
        doc.money("cash_tendered", tendered, instr="Cash handed over by the customer")
        doc.money("change_given", change, w=1.5, instr="Change returned to the customer")
        doc.text("card_last_four", None, instr="Last four digits of the payment card")
    else:
        doc.text("card_last_four", last4, instr="Last four digits of the payment card")
    if ret == "days":
        doc.date("return_by", ret_by, w=1.5, instr="Last day to return items: the purchase date "
                 "plus the return window")
    elif ret == "date":
        doc.date("return_by", ret_by, w=1.2, instr="Last day to return items")
    else:
        doc.date("return_by", None, instr="Last day to return items")
    doc.text("cashier_name", cashier.upper() if (cashier and thermal) else cashier, instr="Name of the cashier")
    doc.text("loyalty_id", loyalty, instr="Customer loyalty or rewards number")
    doc.text("store_vat_number", None, w=0.6, instr="Store's VAT or tax registration number")
    doc.text("store_phone", store_phone if thermal else None, instr="Store phone number")
    doc.text("coupon_code", None, instr="Coupon or promotion code used")
    return doc


# ================================================================ order confirmation email

def order_confirmation(r: random.Random, layout: str) -> Doc:
    doc = Doc(r, "order_confirmation", layout)
    stem = doc.stem()
    shop = f"{stem} {r.choice(('Outfitters', 'Home', 'Goods', 'Direct', 'Living'))}"
    cust = doc.person()
    city = doc.city()[0]
    odate = rand_date(r)
    start = odate + DAY * r.randint(3, 7)
    end = start + DAY * r.randint(1, 3)
    D, noyear = _dates(r, [odate, start, end], odate, 0.6)
    if noyear:
        doc.reference_date = odate
    M = _money(r)
    order_no = code(r, r.choice(("#######", "@@-######", "####-####")))
    lines = []
    for name in r.sample(RETAIL, r.randint(1, 4)):
        qty = r.choice((1, 1, 1, 2, 3))
        unit = r.randint(9, 129) * 100 + r.choice((0, 50, 95, 99))
        lines.append((name, qty, unit, qty * unit))
    subtotal = sum(x[3] for x in lines)
    promo = None
    discount = 0
    if r.random() < 0.3:
        pct = r.choice((10, 15, 20))
        promo = f"{r.choice(('WELCOME', 'SAVE', 'AUTUMN', 'FRIENDS'))}{pct}"
        discount = pct_of(subtotal, pct * 100)
    method = r.choice(("Standard", "Standard", "Express"))
    ship = r.choice((0, 0, 499, 799)) if method == "Standard" else r.choice((1499, 1999, 2499))
    bp = r.choice((0, 600, 725, 825))
    tax = pct_of(subtotal - discount, bp)
    total = subtotal - discount + ship + tax
    last4 = code(r, "####")
    gift = r.choice(("Happy birthday, Leo!", "Congratulations on the new home!",
                     "Thanks for everything - see you soon.")) if r.random() < 0.2 else None
    track_line = r.choice(("We'll email your tracking number as soon as your order ships.",
                           "Tracking number: available once your parcel is dispatched.", ""))
    ship_txt = "Free" if ship == 0 else M(ship)
    window = f"{D(start)} - {D(end)}"

    if layout == "email":
        out = [f"From: {shop} <orders@{slug(stem)}.example>", f"To: {cust} <{_email(cust, 'mail')}>",
               f"Date: {D(odate)}", f"Subject: Order {order_no} confirmed", "",
               f"Hi {_first(cust)},", "",
               r.choice(("Thanks for your order! We're getting it ready.",
                         "Good news - we've received your order.",
                         "Thank you for shopping with us.")),
               f"Order number {order_no}, placed on {D(odate)}.", ""]
        for name, qty, unit, amt in lines:
            out.append(f"{qty} x {name} - {M(amt)}")
        out += ["", f"Subtotal: {M(subtotal)}"]
        if promo:
            out.append(f"Promo code {promo}: -{M(discount)}")
        out += [f"Shipping ({method}): {ship_txt}", f"Tax: {M(tax)}", f"Order total: {M(total)}",
                f"Paid with card ending {last4}.", "",
                f"Estimated delivery: {window}, to {cust}, {doc.street()}, {city}."]
        if gift:
            out.append(f'Gift message: "{gift}"')
        if track_line:
            out.append(track_line)
        out += ["", f"The {shop} team"]
    else:
        out = [f"{shop} - ORDER SUMMARY", "", f"Order: {order_no}", f"Order date: {D(odate)}",
               f"Customer: {cust}", f"Ship to: {doc.street()}, {city}", f"Delivery method: {method}",
               f"Arriving: {window}", ""]
        nw = max(len(x[0]) for x in lines) + 2
        out += _pad([("Item", "Qty", "Price")] + [(n, str(q), M(a)) for n, q, _, a in lines],
                    (nw, 4, 11), "lrr")
        out += ["", f"Items subtotal: {M(subtotal)}"]
        if promo:
            out.append(f"Discount ({promo}): -{M(discount)}")
        out += [f"Shipping: {ship_txt}", f"Estimated tax: {M(tax)}", f"Total charged: {M(total)}",
                f"Payment: card ending {last4}"]
        if gift:
            out.append(f"Gift message: {gift}")
        if track_line:
            out += ["", track_line]
        out += ["", "Need to change something? Reply within one hour of ordering."]
    doc.state = "\n".join(out)

    doc.text("order_number", order_no, w=2)
    doc.text("retailer", shop, instr="Shop the order was placed with")
    doc.text("customer_name", cust)
    doc.date("order_date", odate)
    doc.text("ship_to_city", city, instr="City of the delivery address")
    doc.items("item_names", [x[0] for x in lines], "text", instr="Name of each product ordered")
    doc.number("units_ordered", sum(x[1] for x in lines), integer=True,
               instr="Total number of units ordered (the sum of the quantities)")
    doc.money("order_total", total, w=2, instr="Total charged for the order")
    doc.money("subtotal", subtotal, instr="Items subtotal before discounts, shipping and tax")
    doc.money("shipping_cost", ship, instr="Shipping charge (0 if free)")
    if promo:
        doc.money("discount_amount", discount, instr="Discount from the promo code")
    doc.text("promo_code", promo, instr="Promotion code applied to the order")
    doc.date("delivery_earliest", start, w=1.5, instr="First day of the estimated delivery window")
    doc.date("delivery_latest", end, w=1.5, instr="Last day of the estimated delivery window")
    doc.duration("days_to_latest_delivery", (end - odate).days, "days", integer=True, w=1.5,
                 instr="Days from the order date to the last day of the delivery window")
    doc.text("card_last_four", last4, instr="Last four digits of the payment card")
    doc.text("gift_message", gift, instr="Gift message included with the order")
    doc.text("tracking_number", None, w=1.5, instr="Shipment tracking number")
    doc.date("ship_date", None, instr="Date the order was shipped")
    return doc


# ================================================================ shipping / delivery notice

def shipping_notice(r: random.Random, layout: str) -> Doc:
    doc = Doc(r, "shipping_notice", layout)
    carrier = f"{doc.stem()} {r.choice(('Parcel', 'Express', 'Courier', 'Freight'))}"
    sender = f"{doc.stem()} {r.choice(('Outfitters', 'Home', 'Goods', 'Direct'))}"
    recip = doc.person()
    origin, _ = doc.city()
    dest, _ = doc.city(avoid=[origin])
    hub, _ = doc.city(avoid=[origin, dest])
    tracking = r.choice((code(r, "@@#########@@"), code(r, "1@##########"), code(r, "#### #### ####")))
    order_no = code(r, "#######")
    service = r.choice(("Ground", "2-Day", "Express Saver", "Standard"))
    ship = rand_date(r)
    est = ship + DAY * r.randint(2, 6)
    delayed = r.random() < 0.45
    final = est + DAY * r.randint(1, 4) if delayed else est
    notice = ship + DAY * r.randint(1, (est - ship).days)  # the notice is sent before delivery
    D, noyear = _dates(r, [ship, est, final, notice, ship - DAY], notice, 0.55)
    if noyear:
        doc.reference_date = notice
    has_window = r.random() < 0.7
    w_start = rand_minutes(r, "08:00", "15:00", 30)
    w_end = w_start + r.choice((120, 180, 240))
    tstyle = r.choice(TIME_STYLES)
    T = lambda m: ftime(m, tstyle)
    pieces = r.randint(1, 3)
    wunit = r.choice(("kg", "lb"))
    weight = round(r.randint(4, 240) / 10, 1) if r.random() < 0.6 else None
    reason = r.choice(("severe weather", "a missed connection at our hub", "high parcel volumes",
                       "an address check"))
    # tracking events: label, pickup, hub arrival, hub departure, maybe delay, last scan
    ev = [(ship - DAY, rand_minutes(r, "15:00", "21:00", 1), origin, "Label created"),
          (ship, rand_minutes(r, "09:00", "18:00", 1), origin, "Picked up"),
          (ship, rand_minutes(r, "19:00", "23:30", 1), origin, "Departed facility")]
    hub_day = ship + DAY * min(1, (notice - ship).days)
    ev.append((hub_day, rand_minutes(r, "04:00", "09:00", 1), hub, "Arrived at sort hub"))
    if delayed and notice > hub_day:
        ev.append((notice, rand_minutes(r, "06:00", "11:00", 1), hub, f"Delayed: {reason}"))
    elif notice > hub_day:
        ev.append((notice, rand_minutes(r, "06:00", "11:00", 1), hub, "In transit"))
    last = ev[-1]

    if layout == "email":
        out = [f"From: {carrier} <notifications@{slug(carrier)}.example>",
               f"Date: {D(notice)}",
               f"Subject: {'Delivery update' if delayed else 'Your package is on its way'}: {tracking}", "",
               f"Hi {_first(recip)},", "",
               f"Your {sender} order {order_no} shipped on {D(ship)} with {carrier} ({service}).",
               f"Tracking number: {tracking}", ""]
        if delayed:
            out.append(f"Your delivery date has changed because of {reason}. It was expected on "
                       f"{D(est)} and is now scheduled for {D(final)}.")
        else:
            out.append(f"Expected delivery: {D(est)}.")
        if has_window:
            out.append(f"Delivery window: {T(w_start)} - {T(w_end)}")
        else:
            out.append("Your delivery window will be shared on the morning of delivery.")
        pw = f"{pieces} package{'s' if pieces > 1 else ''}"
        out.append(f"Shipment: {pw}" + (f", total weight {weight} {wunit}." if weight else "."))
        out += [f"Delivering to: {recip}, {dest}", "",
                "Not home? You can choose a safe place or a pickup point in the app.",
                f"- {carrier} Customer Care"]
    else:
        out = [f"{carrier} - Shipment details", "", f"Tracking number: {tracking}",
               f"Service: {service}", f"Status: {'Delayed' if delayed else 'In transit'}",
               f"Shipped: {D(ship)}"]
        if delayed:
            out.append(f"Original estimate: {D(est)}")
        out.append(f"Scheduled delivery: {D(final)}")
        out.append(f"Delivery window: {T(w_start)}-{T(w_end)}" if has_window
                   else "Delivery window: not yet available")
        out.append(f"Pieces: {pieces}" + (f"   Weight: {weight} {wunit}" if weight else ""))
        out.append(f"Ship to: {recip}, {dest}")
        has_ref = r.random() < 0.6
        if has_ref:
            out.append(f"Reference: {sender} order {order_no}")
        out += ["", "Travel history (local time)"]
        for d, m, place, status in reversed(ev):
            out.append(f"{D(d)}  {T(m)}  {place.ljust(18)}{status}")
        if not has_ref:
            order_no = None
    doc.state = "\n".join(out)

    doc.text("tracking_number", tracking, w=2)
    doc.text("carrier", carrier, instr="Delivery company")
    doc.text("recipient_name", recip)
    doc.text("destination_city", dest, instr="City the package is being delivered to")
    doc.date("ship_date", ship, instr="Date the package shipped")
    doc.date("delivery_date", final, w=3, instr="Currently scheduled delivery date (the latest "
             "estimate if it changed)")
    if delayed:
        doc.date("original_delivery_date", est, w=1.5, instr="Delivery date first estimated, "
                 "before the change")
    doc.duration("transit_days", (final - ship).days, "days", integer=True, w=1.5,
                 instr="Days from the ship date to the scheduled delivery date")
    doc.time("delivery_window_start", w_start if has_window else None, w=1.2,
             instr="Start of the delivery time window")
    doc.time("delivery_window_end", w_end if has_window else None,
             instr="End of the delivery time window")
    doc.number("package_count", pieces, integer=True, instr="Number of packages in the shipment")
    doc.number("weight", weight, unit=wunit, decimals=1, instr=f"Total shipment weight in {wunit}")
    doc.text("order_number", order_no, instr=f"{sender} order number")
    if layout != "email":
        doc.datetime("last_scan_datetime", last[0], last[1], w=1.5,
                     instr="Date and time of the most recent tracking event")
        doc.text("last_scan_location", last[2], instr="Location of the most recent tracking event")
    doc.text("delivery_instructions", None, instr="Delivery instructions left by the recipient")
    doc.money("declared_value", None, instr="Declared value of the shipment")
    return doc


# ================================================================ bank statement excerpt

def bank_statement(r: random.Random, layout: str) -> Doc:
    doc = Doc(r, "bank_statement", layout)
    bank = f"{doc.stem()} {r.choice(('Savings Bank', 'Credit Union', 'Bank', 'Trust Bank'))}"
    holder = doc.person()
    last4 = code(r, "####")
    y, mo = r.choice((2025, 2026)), r.randint(1, 12)
    start = dt.date(y, mo, 1)
    end = (dt.date(y + (mo == 12), mo % 12 + 1, 1) - DAY)
    ndays = (end - start).days + 1
    merchant = f"{doc.stem().upper()} {r.choice(('CAFE', 'GROCERY', 'FUEL', 'BOOKS', 'PHARMACY'))}"
    employer = doc.company(("Logistics", "Foods", "Health", "Analytics"), legal=False)[1].upper()
    tx = []  # (date, description, cents: + credit / - debit)
    for k in sorted(r.sample(range(ndays), r.randint(2, 3))):
        tx.append((start + DAY * k, f"CARD PURCHASE {merchant}", -r.randint(450, 8900)))
    tx.append((start + DAY * r.randint(0, ndays - 1), f"DIRECT DEPOSIT {employer} PAYROLL",
               r.randint(1800, 5200) * 100 + r.randint(0, 99)))
    others = [
        (f"UTILITY PAYMENT {doc.stem().upper()} ENERGY", -r.randint(4500, 21000)),
        ("TRANSFER TO SAVINGS", -r.choice((10000, 20000, 25000, 50000))),
        (f"ATM WITHDRAWAL {doc.city()[0].upper()}", -r.choice((4000, 6000, 10000, 20000))),
        (f"CARD PURCHASE {doc.stem().upper()} HARDWARE", -r.randint(800, 15000)),
        (f"RENT PAYMENT {doc.stem().upper()} PROPERTIES", -r.randint(900, 2400) * 100),
        (f"REFUND {doc.stem().upper()} OUTFITTERS", r.randint(1500, 9000)),
        ("INTEREST PAID", r.randint(5, 900)),
    ]
    for desc, c in r.sample(others, r.randint(2, 4)):
        tx.append((start + DAY * r.randint(0, ndays - 1), desc, c))
    tx.sort(key=lambda t: t[0])
    debits = [-c for _, _, c in tx if c < 0]
    credits = [c for _, _, c in tx if c > 0]
    opening = sum(debits) + r.randint(5000, 600000)
    closing = opening + sum(credits) - sum(debits)
    payroll = next(c for _, d, c in tx if "PAYROLL" in d)
    m_dates = [d for d, desc, _ in tx if desc.endswith(merchant)]
    m_total = sum(-c for _, desc, c in tx if desc.endswith(merchant))
    yearless_rows = r.random() < 0.6
    D, _ = _dates(r, [start, end], None)
    if yearless_rows:
        doc.reference_date = end
        rowdate = lambda d: f"{d.day:02d} {MON[d.month - 1]}"  # "02 Sep"
    else:
        rowdate = lambda d: d.isoformat()
    branch_city = doc.city()[0]
    branch = f"{branch_city} branch" if r.random() < 0.3 else None

    if layout == "table":
        out = [bank, "Statement of account", "", f"Account holder: {holder}",
               f"Account: Everyday Checking ****{last4}", f"Statement period: {D(start)} to {D(end)}"]
        if branch:
            out.append(f"Branch: {branch}")
        out.append("")
        rows = [("Date", "Description", "Debit", "Credit", "Balance"), ("", "Opening balance", "", "", fnum(opening))]
        bal = opening
        for d, desc, c in tx:
            bal += c
            rows.append((rowdate(d), desc, fnum(-c) if c < 0 else "", fnum(c) if c > 0 else "", fnum(bal)))
        rows.append(("", "Closing balance", "", "", fnum(closing)))
        dw = max(len(x[1]) for x in rows) + 1
        out += _pad(rows, (10 if not yearless_rows else 6, dw, 9, 9, 10), "llrrr")
        out += ["", "Amounts in USD. Please report any discrepancy within 30 days."]
    else:
        M = _money(r)
        out = [f"{bank} | Account summary", "", f"Name: {holder}",
               f"Account number: XXXX-XXXX-{last4}", f"Period: {D(start)} - {D(end)}", "",
               f"Opening balance: {M(opening)}", f"Total credits: {M(sum(credits))}",
               f"Total debits: {M(sum(debits))}", f"Closing balance: {M(closing)}", "", "Transactions"]
        for d, desc, c in tx:
            out.append(f"{rowdate(d)}  {desc.ljust(46)} {('+' if c > 0 else '-') + M(abs(c))}")
        if branch:
            out += ["", f"Your branch: {branch}"]
        out += ["", "Debits are shown with a minus sign."]
    doc.state = "\n".join(out)

    doc.text("account_holder", holder)
    doc.text("account_last_four", last4, instr="Last four digits of the account number")
    doc.date("statement_start", start, instr="First day of the statement period")
    doc.date("statement_end", end, instr="Last day of the statement period")
    doc.money("opening_balance", opening)
    doc.money("closing_balance", closing, w=2)
    if layout != "table":
        doc.money("total_debits", sum(debits), instr="Total of all debits (money out)")
    doc.money("largest_debit", max(debits), w=1.5, instr="Largest single debit (money out)")
    doc.money("payroll_deposit", payroll, instr=f"Amount of the payroll deposit from {employer}")
    doc.items("merchant_purchase_dates", m_dates, "date", w=2,
              instr=f"Dates of all card purchases at {merchant}")
    doc.money("merchant_total", m_total, w=1.5, instr=f"Total spent at {merchant} in the period")
    doc.number("transaction_count", len(tx), integer=True,
               instr="Number of transactions listed (not counting opening and closing balances)")
    doc.text("branch", branch, alts=[branch_city], instr="Branch of the account")
    doc.money("overdraft_limit", None, instr="Arranged overdraft limit")
    doc.number("interest_rate", None, instr="Annual interest rate on the account, in percent")
    doc.text("iban", None, w=0.8, instr="IBAN of the account")
    doc.items("cheque_numbers", None, "text", w=0.6, instr="Numbers of any cheques listed")
    return doc


# ================================================================ timesheet

def timesheet(r: random.Random, layout: str) -> Doc:
    doc = Doc(r, "timesheet", layout)
    company, _ = doc.company(("Logistics", "Engineering", "Foods", "Health", "Studio"))
    emp, mgr = doc.person(), doc.person()
    emp_id = code(r, r.choice(("E-#####", "EMP####", "#####")))
    d0 = rand_date(r)
    week = d0 - DAY * d0.weekday()
    codes = r.sample(("PRJ-1042", "PRJ-2210", "OPS-077", "MNT-310", "ADM-001", "CLT-4471"), r.randint(2, 3))
    off = r.choice((None, None, 1, 2, 3, 4))  # a weekday off (index)
    entries = []  # (date, start, end, break, work minutes, code)
    for i in range(5):
        d = week + DAY * i
        if i == off:
            continue
        s = rand_minutes(r, "07:00", "09:30", 15)
        brk = r.choice((30, 30, 45, 60))
        work = 15 * r.randint(24, 38)
        entries.append((d, s, s + brk + work, brk, work, r.choice(codes)))
    total = sum(e[4] for e in entries)
    approved = r.random() < 0.6
    sub = week + DAY * 4
    appr_date = sub + DAY * r.randint(1, 4)
    dept = r.choice(("Operations", "Warehouse", "Field Service", "Finance")) if r.random() < 0.5 else None
    D, noyear = _dates(r, [week, sub, appr_date], appr_date if approved else sub, 0.35, weekday=False)
    if noyear:
        doc.reference_date = appr_date if approved else sub
    tstyle = r.choice(("24", "24", "12", "12l"))
    T = lambda m: ftime(m, tstyle)
    hrs = lambda m: f"{m / 60:.2f}"

    if layout == "table":
        out = [f"{company} - Weekly timesheet", "", f"Employee: {emp} ({emp_id})"]
        if dept:
            out.append(f"Department: {dept}")
        out += [f"Week starting: {D(week)}", ""]
        rows = [("Day", "Date", "Start", "End", "Break", "Hours", "Project")]
        for i in range(5):
            d = week + DAY * i
            e = next((x for x in entries if x[0] == d), None)
            if e:
                rows.append((WEEKDAYS[i][:3], D(d), T(e[1]), T(e[2]), f"{e[3]} min", hrs(e[4]), e[5]))
            else:
                rows.append((WEEKDAYS[i][:3], D(d), "-", "-", "-", "0.00", "Annual leave"))
        dw = max(len(x[1]) for x in rows)
        tw = max(len(x[k]) for x in rows for k in (2, 3))
        out += _pad(rows, (4, dw, tw, tw, 7, 6, 12), "lllllrl")
        out += ["", f"Total hours: {hrs(total)}", f"Submitted: {D(sub)}"]
        out.append(f"Approved by {mgr} on {D(appr_date)}" if approved else
                   r.choice(("Status: pending approval", "Approval: awaiting manager review")))
    else:
        mail = f"{slug(company.split()[0])}.example"
        msg = [f"From: {emp} <{slug(_first(emp))}@{mail}>", f"To: {mgr} <{slug(_first(mgr))}@{mail}>",
               f"Date: {D(sub)}", f"Subject: Timesheet, week of {D(week)}", "",
               f"Hi {_first(mgr)},", "", f"Here are my hours for the week starting {D(week)}:", ""]
        for i in range(5):
            d = week + DAY * i
            e = next((x for x in entries if x[0] == d), None)
            if e:
                msg.append(f"{WEEKDAYS[i]} {D(d)}: {T(e[1])} to {T(e[2])}, {e[3]} min unpaid break ({e[5]})")
            else:
                msg.append(f"{WEEKDAYS[i]} {D(d)}: annual leave")
        msg += ["", f"That makes {hrs(total)} hours in total.", "", "Thanks,", emp,
                f"Employee ID {emp_id}" + (f", {dept}" if dept else "")]
        if approved:
            reply = [f"From: {mgr}", f"Date: {D(appr_date)}", f"Subject: RE: Timesheet, week of {D(week)}", "",
                     r.choice(("Approved, thanks.", "Looks good - approved.", "Approved.")), _first(mgr),
                     "", "-----Original message-----"]
            msg = reply + msg
        out = msg
    doc.state = "\n".join(out)

    pick = r.sample(entries, min(3, len(entries)))
    e1, e2, e3 = pick[0], pick[1 % len(pick)], pick[2 % len(pick)]
    wd = lambda e: WEEKDAYS[e[0].weekday()].lower()
    doc.text("employee_name", emp)
    doc.text("employee_id", emp_id)
    doc.date("week_start", week, instr="First day of the timesheet week")
    doc.duration("total_hours", total / 60, "hours", decimals=2, w=1.5,
                 instr="Total hours worked in the week")
    doc.duration(f"hours_{wd(e1)}", e1[4] / 60, "hours", decimals=2, w=2,
                 instr=f"Hours worked on {wd(e1).title()}: end time minus start time minus the unpaid break")
    doc.time(f"start_time_{wd(e2)}", e2[1], w=1.2, instr=f"Start time on {wd(e2).title()}")
    doc.time(f"end_time_{wd(e3)}", e3[2], instr=f"End time on {wd(e3).title()}")
    if e3 is not e1:
        doc.duration(f"break_{wd(e3)}", e3[3], "minutes", integer=True,
                     instr=f"Unpaid break on {wd(e3).title()}")
    doc.items("dates_worked", [e[0] for e in entries], "date", w=1.5, instr="Dates on which hours were worked")
    doc.items("project_codes", list(dict.fromkeys(e[5] for e in entries)), "text",
              instr="Distinct project codes, in order of first appearance")
    doc.text("approved_by", mgr if approved else None, w=1.5,
             instr="Manager who approved the timesheet")
    doc.date("approval_date", appr_date if approved else None, instr="Date the timesheet was approved")
    doc.text("department", dept)
    doc.text("cost_center", None, instr="Cost centre code")
    doc.money("hourly_rate", None, instr="Employee's hourly pay rate")
    return doc


# ================================================================ flight itinerary

def flight_itinerary(r: random.Random, layout: str) -> Doc:
    doc = Doc(r, "flight_itinerary", layout)
    stem = doc.stem()
    airline = f"{stem} {r.choice(('Air', 'Airways', 'Airlines'))}"
    iata = stem[:2].upper()
    ref = code(r, "******")
    pax = [doc.person() for _ in range(r.choice((1, 1, 2, 2, 3)))]
    o, oc = doc.city()
    (dst, dc) = doc.city(avoid=[o])
    (via, vc) = doc.city(avoid=[o, dst])
    connect = r.random() < 0.45
    tz = {o: r.randint(-3, 3), via: r.randint(-3, 3), dst: r.randint(-3, 3)}

    def fly(a: str, b: str, dep: int) -> tuple[int, int]:
        """(flight minutes, local arrival) with consistent city offsets."""
        shift = 60 * (tz[b] - tz[a])
        dur = max(5 * r.randint(11, 66), 45 - shift)
        return dur, dep + dur + shift

    dep_date = rand_date(r)
    dep1 = rand_minutes(r, "06:00", "21:00", 5)
    dur1, arr1 = fly(o, via if connect else dst, dep1)
    legs = [(f"{iata}{r.randint(100, 989)}", o, oc, (via, vc) if connect else (dst, dc), dep1, arr1, dur1)]
    lay = None
    if connect:
        lay = 5 * r.randint(9, 42)
        dep2 = arr1 + lay
        dur2, arr2 = fly(via, dst, dep2)
        legs.append((f"{iata}{r.randint(100, 989)}", via, vc, (dst, dc), dep2, arr2, dur2))
    final_arr = legs[-1][5]
    round_trip = r.random() < 0.5
    ret_date = dep_date + DAY * r.randint(2, 14)
    ret_dep = rand_minutes(r, "07:00", "20:00", 5)
    ret_dur, ret_arr = fly(dst, o, ret_dep)
    ret_no = f"{iata}{r.randint(100, 989)}"
    per = r.randint(89, 1200) * 100 - 1
    total = per * len(pax)
    taxes = pct_of(total, r.choice((900, 1200, 1500)))
    bags = r.choice((0, 1, 1, 2))
    seat = f"{r.randint(3, 38)}{r.choice('ABCDEF')}" if (len(pax) == 1 and r.random() < 0.5) else None
    ff = f"{iata} {code(r, '########')}" if r.random() < 0.3 else None
    cur = r.choice(("USD", "USD", "EUR"))
    M = _money(r, cur)
    issue = dep_date - DAY * r.randint(3, 60)
    D, noyear = _dates(r, [issue, dep_date] + ([ret_date] if round_trip else []), issue, 0.35)
    if noyear:
        doc.reference_date = issue
    tstyle = r.choice(("24", "24", "12"))
    T = lambda m: ftime(m, tstyle)
    dstyle = r.choice(("hm", "hr_min"))

    def day_of(m: int) -> dt.date:
        return dep_date + DAY * (m // 1440)

    if layout == "eticket":
        out = [f"{airline} - e-ticket receipt", "", f"Booking reference: {ref}", f"Issued: {D(issue)}",
               "Passengers: " + ", ".join(pax), "", f"OUTBOUND  {D(dep_date)}"]
        for no, a, ac, (b, bc), dp, ar, du in legs:
            arr_txt = T(ar) + (f" (+1, {D(day_of(ar))})" if ar >= 1440 else "")
            dep_txt = T(dp) + (f" ({D(day_of(dp))})" if dp >= 1440 else "")
            out.append(f"  {no}  {a} ({ac}) {dep_txt}  ->  {b} ({bc}) {arr_txt}   Duration {fdur_hm(du, dstyle)}")
        if round_trip:
            ra = ret_arr
            out += ["", f"RETURN  {D(ret_date)}",
                    f"  {ret_no}  {dst} ({dc}) {T(ret_dep)}  ->  {o} ({oc}) {T(ra % 1440)}"
                    + (" (+1)" if ra >= 1440 else "") + f"   Duration {fdur_hm(ret_dur, dstyle)}"]
        else:
            out += ["", "One-way ticket."]
        out += ["", f"Checked baggage: {bags} bag{'s' if bags != 1 else ''} per passenger"
                + (" (23 kg each)" if bags else ", cabin bag only")]
        if len(pax) == 1:
            out.append(f"Seat: {seat}" if seat else "Seat: assigned at check-in")
        if ff:
            out.append(f"Frequent flyer: {ff}")
        out += [f"Fare paid: {M(total)} (incl. taxes and fees of {M(taxes)})", "",
                "All times are local. Gates close 20 minutes before departure."]
    else:
        out = [f"From: {airline} <bookings@{slug(airline)}.example>", f"Date: {D(issue)}",
               f"Subject: Your trip to {dst} is confirmed ({ref})", "", f"Hi {_first(pax[0])},", "",
               f"Thanks for booking with {airline}. Your booking reference is {ref}.", ""]
        no, a, ac, (b, bc), dp, ar, du = legs[0]
        nxt = lambda m: f" on {D(day_of(m))}" if m >= 1440 else ""
        if connect:
            no2, _, _, _, dp2, ar2, _ = legs[1]
            out.append(f"On {D(dep_date)}, flight {no} leaves {a} at {T(dp)} and lands in {b} at "
                       f"{T(ar)}{nxt(ar)} (flight time {fdur_hm(du, dstyle)}). Your connecting flight {no2} "
                       f"departs {b} at {T(dp2)}{nxt(dp2)} and arrives in {dst} at {T(ar2)}{nxt(ar2)}.")
        else:
            out.append(f"On {D(dep_date)}, flight {no} leaves {a} at {T(dp)} and arrives in {dst} at "
                       f"{T(ar)}{nxt(ar)} (flight time {fdur_hm(du, dstyle)}).")
        if round_trip:
            out.append(f"You fly home on {D(ret_date)} with flight {ret_no}, departing {dst} at {T(ret_dep)}.")
        else:
            out.append("This is a one-way booking.")
        out += ["", "Travellers: " + "; ".join(pax),
                f"Baggage: {bags} checked bag{'s' if bags != 1 else ''} each" if bags else
                "Baggage: cabin bag only, no checked bags"]
        if len(pax) == 1:
            out.append(f"Seat: {seat}" if seat else "Seats are assigned at online check-in.")
        if ff:
            out.append(f"Frequent flyer number on file: {ff}")
        out += [f"Total paid: {M(total)}", "", "Gate information is shown at the airport on the day.",
                "All times are local to each airport.", f"- {airline}"]
    doc.state = "\n".join(out)

    a_day = day_of(final_arr)
    doc.text("booking_reference", ref, w=2)
    doc.text("airline", airline)
    doc.items("passenger_names", pax, "text", w=1.5, instr="Names of all passengers")
    doc.text("first_flight_number", legs[0][0], instr="Flight number of the first outbound flight")
    doc.datetime("departure_datetime", dep_date, dep1, w=2,
                 instr="Departure of the first outbound flight (local time)")
    doc.datetime("arrival_datetime", a_day, final_arr % 1440, w=2,
                 instr="Arrival at the final destination of the outbound journey (local time)")
    doc.text("destination_city", dst, instr="Final destination city of the outbound journey")
    doc.duration("first_flight_minutes", dur1, "minutes", integer=True,
                 instr="Flight time of the first outbound flight")
    if connect:
        doc.duration("layover_minutes", lay, "minutes", integer=True, w=2,
                     instr="Connection time between the two outbound flights: second departure "
                     "minus first arrival")
    doc.money("total_fare", total, cur, instr="Total amount paid for the booking")
    doc.number("checked_bags", bags, integer=True, instr="Checked bags included per passenger")
    doc.date("return_date", ret_date if round_trip else None, w=1.2, instr="Date of the return flight")
    doc.time("return_departure_time", ret_dep if round_trip else None,
             instr="Departure time of the return flight")
    if len(pax) == 1:
        doc.text("seat_number", seat, w=1.2, instr="Assigned seat")
    doc.text("frequent_flyer_number", ff)
    doc.text("gate", None, instr="Departure gate of the first flight")
    doc.text("meal_preference", None, w=0.6, instr="Special meal requested")
    return doc


# ================================================================ hotel booking

def hotel_booking(r: random.Random, layout: str) -> Doc:
    doc = Doc(r, "hotel_booking", layout)
    stem = doc.stem()
    short = f"{stem} {r.choice(('Hotel', 'Inn', 'Suites', 'Lodge', 'House Hotel'))}"
    hotel = ("The " + short) if r.random() < 0.4 else short
    city = doc.city()[0]
    guest = doc.person()
    conf = code(r, r.choice(("#########", "@@-######", "#####@@")))
    ci = rand_date(r)
    nights = r.choice((1, 2, 2, 3, 3, 4, 5, 7))
    co = ci + DAY * nights
    booked = ci - DAY * r.randint(5, 80)
    adults, kids = r.choice((1, 2, 2, 2, 3)), r.choice((0, 0, 0, 1, 2))
    cit = r.choice((14, 15, 15, 16)) * 60
    cot = r.choice((10, 11, 11, 12)) * 60
    room = r.choice(("Standard King", "Deluxe Double", "Superior Twin", "Junior Suite", "Family Room"))
    cur = r.choice(("USD", "USD", "EUR", "GBP"))
    M = _money(r, cur)
    rate = r.randint(89, 420) * 100
    room_total = rate * nights
    taxes = pct_of(room_total, r.choice((1000, 1200, 1350, 1500)))
    total = room_total + taxes
    refundable = r.random() < 0.65
    cdl_day = ci - DAY * r.randint(1, 3)
    cdl_min = r.choice((12 * 60, 18 * 60, 23 * 60 + 59))
    breakfast = r.random() < 0.5
    loyalty = code(r, "########") if r.random() < 0.3 else None
    D, noyear = _dates(r, [booked, ci, co, cdl_day], booked, 0.4)
    if noyear:
        doc.reference_date = booked
    tstyle = r.choice(TIME_STYLES)
    T = lambda m: ftime(m, tstyle)
    guests = f"{adults} adult{'s' if adults > 1 else ''}" + (
        f", {kids} child{'ren' if kids > 1 else ''}" if kids else "")
    canc = (f"Free cancellation until {T(cdl_min)} on {D(cdl_day)} (hotel local time). After that, "
            f"the first night is charged." if refundable else
            "This is a non-refundable rate: no free cancellation, changes or refunds.")

    if layout == "email":
        out = [f"From: {hotel} Reservations <stay@{slug(stem)}.example>", f"Date: {D(booked)}",
               f"Subject: Booking confirmed - {hotel}, {D(ci)}", "", f"Dear {guest},", "",
               f"Thank you for choosing {hotel} in {city}. Your reservation is confirmed.", "",
               f"Confirmation number: {conf}",
               f"Check-in: {D(ci)}, from {T(cit)}", f"Check-out: {D(co)}, until {T(cot)}",
               f"Room: {room}, {guests}",
               f"Rate: {M(rate)} per night x {nights} night{'s' if nights > 1 else ''} = {M(room_total)}",
               f"Taxes and fees: {M(taxes)}", f"Total: {M(total)}", "", canc,
               "Breakfast is included." if breakfast else "Breakfast is available at the restaurant for an extra charge."]
        if loyalty:
            out.append(f"Your member number {loyalty} has been added to the booking.")
        out += ["", "We look forward to welcoming you.", f"{hotel}, {doc.street()}, {city}"]
    else:
        out = ["RESERVATION CONFIRMATION", "", f"Hotel: {hotel}, {doc.street()}, {city}", f"Guest: {guest}",
               f"Confirmation no.: {conf}", f"Booked on: {D(booked)}", f"Arrival: {D(ci)}",
               f"Departure: {D(co)}", f"Room type: {room}", f"Guests: {guests}",
               f"Nightly rate: {M(rate)}", f"Room charges: {M(room_total)}", f"Taxes & fees: {M(taxes)}",
               f"Total for stay: {M(total)}", f"Check-in from {T(cit)}; check-out by {T(cot)}",
               f"Breakfast: {'included' if breakfast else 'not included'}",
               f"Cancellation policy: {canc}"]
        if r.random() < 0.6:
            out.append("Room number: assigned at check-in")
        if loyalty:
            out.append(f"Loyalty member: {loyalty}")
    doc.state = "\n".join(out)

    doc.text("confirmation_number", conf, w=2)
    doc.text("hotel_name", hotel, alts=[short] if hotel != short else None)
    doc.text("guest_name", guest)
    doc.date("check_in_date", ci)
    doc.date("check_out_date", co, w=1.2)
    doc.duration("nights", nights, "days", integer=True, w=2,
                 instr="Length of stay in nights: check-out date minus check-in date")
    doc.time("check_in_time", cit, w=1.2, instr="Earliest check-in time")
    doc.time("check_out_time", cot, instr="Latest check-out time")
    doc.datetime("cancellation_deadline", cdl_day if refundable else None, cdl_min, w=2,
                 instr="Last moment the booking can be cancelled free of charge")
    doc.money("nightly_rate", rate, cur, instr="Room rate per night")
    doc.money("taxes_and_fees", taxes, cur)
    doc.money("total_price", total, cur, w=2, instr="Total price of the stay including taxes")
    doc.text("room_type", room)
    doc.number("guest_count", adults + kids, integer=True, instr="Total number of guests (adults plus children)")
    doc.text("room_number", None, w=1.2, instr="Assigned room number")
    doc.text("loyalty_number", loyalty, instr="Guest's loyalty programme number")
    doc.money("parking_fee", None, cur, instr="Parking charge per night")
    return doc
