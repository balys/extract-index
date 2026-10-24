"""`docs` families, part B: meeting thread, support ticket, maintenance log, payslip, purchase
order, utility bill, lease summary, incident report."""

from __future__ import annotations

import datetime as dt
import random

from .docs_fam_a import _dates, _email, _first, _money, _pad
from .docs_kit import (WEEKDAYS, Doc, add_months, amount, code, fdate, fnum, ftime, hhmm, number_word, pct_of,
                       rand_date, rand_minutes, slug)

DAY = dt.timedelta(days=1)


def rel_day(r: random.Random, sent: dt.date) -> tuple[str, dt.date]:
    """A relative day phrase that a careful reader resolves to exactly one date, given the
    (weekday) date the message was sent: "tomorrow", "on Thursday" later in the same week, or
    "<weekday> next week"."""
    w = sent.weekday()
    opts = []
    if w <= 3:
        opts.append(("tomorrow", sent + DAY))
    for k in range(w + 2, 5):
        opts.append((f"on {WEEKDAYS[k]}", sent + DAY * (k - w)))
        opts.append((f"this {WEEKDAYS[k]}", sent + DAY * (k - w)))
    for k in range(5):
        opts.append((f"{WEEKDAYS[k]} next week", sent + DAY * (7 - w + k)))
    return r.choice(opts)


def _hdr_dt(d: dt.date, minutes: int, year_style: str) -> str:
    return f"{fdate(d, year_style)} {hhmm(minutes)}"


# ================================================================ meeting invite / reschedule thread

TOPICS = ("Q3 budget review", "Vendor onboarding kickoff", "Website redesign sync",
          "Warehouse layout review", "Hiring plan for Q1", "Customer renewal strategy",
          "Security audit follow-up", "Product launch checklist", "Quarterly planning",
          "Pricing update review", "Fleet replacement options", "Office move planning")
ROOMS = ("Room 4B", "Room 2.14", "Harbor Room", "Boardroom (3rd floor)", "Juniper meeting room",
         "Room 112")
CONFLICTS = ("I'm at a client site that afternoon", "I have a dentist appointment then",
             "that clashes with the board prep", "I'm travelling that day",
             "the finance close runs until late that day")


def meeting_thread(r: random.Random, layout: str) -> Doc:
    doc = Doc(r, "meeting_thread", layout)
    co_short = doc.company(("Logistics", "Foods", "Analytics", "Health"), legal=False)[1]
    org = doc.person()
    atts = [doc.person() for _ in range(r.randint(2, 5))]
    added = doc.person() if r.random() < 0.35 else None
    optional = [doc.person()] if (layout == "invite" and r.random() < 0.4) else []
    topic = r.choice(TOPICS)
    sent1 = rand_date(r)
    sent1 = sent1 - DAY * sent1.weekday() + DAY * r.randint(0, 1)  # a Monday or Tuesday
    orig_day = sent1 + DAY * r.randint(2, 3)
    o_start = rand_minutes(r, "09:00", "16:00", 30)
    dur = r.choice((30, 45, 60, 60, 90))
    sent2 = sent1 + DAY
    sent3 = sent2 + DAY * r.randint(0, 1)
    phrase, new_day = rel_day(r, sent3)
    while new_day == orig_day:
        phrase, new_day = rel_day(r, sent3)
    n_start = rand_minutes(r, "09:00", "16:30", 30)
    new_dur = dur if r.random() < 0.7 else r.choice([x for x in (30, 45, 60, 90) if x != dur])
    video = r.random() < 0.3
    room = "video call" if video else r.choice(ROOMS)
    moved_room = (not video) and r.random() < 0.3
    final_room = r.choice([x for x in ROOMS if x != room]) if moved_room else room
    requester = atts[0]
    t1 = rand_minutes(r, "08:00", "11:00", 1)
    t2 = rand_minutes(r, "12:00", "17:00", 1)
    t3 = rand_minutes(r, "08:00", "17:30", 1) if sent3 > sent2 else t2 + r.randint(10, 50)
    ystyle = r.choice(("dmy", "mdy", "wd_dmy", "iso"))
    tstyle = r.choice(("12", "12short", "24"))
    T = lambda m: ftime(m, tstyle)
    D, _ = _dates(r, [orig_day, new_day], None)
    dur_txt = {30: "30 minutes", 45: "45 minutes", 60: "an hour", 90: "90 minutes"}

    if layout == "thread":
        doc.reference_date = sent3
        explicit = r.random() < 0.3
        when = f"{phrase} ({D(new_day)})" if explicit else phrase
        if new_dur == dur:
            length = r.choice((f"still {dur_txt[dur]}", f"same length ({dur_txt[dur]})"))
        else:
            length = f"but only {dur_txt[new_dur]} this time" if new_dur < dur else f"and let's take {dur_txt[new_dur]}"
        place = (f"in {final_room} instead" if moved_room else
                 "same video link" if video else "same room")
        m1 = [f"From: {org} <{_email(org, co_short)}>", "To: " + ", ".join(atts),
              f"Sent: {_hdr_dt(sent1, t1, ystyle)}", f"Subject: {topic}", "",
              "Hi all,", "",
              f"Let's meet on {D(orig_day)} from {T(o_start)} to {T(o_start + dur)} "
              + ("on a video call (link to follow)" if video else f"in {room}") + f" for the {topic.lower()}.",
              r.choice(("Please bring your updated numbers.", "Agenda to follow.",
                        "I'll share the draft beforehand.")), "", _first(org)]
        m2 = [f"From: {requester}", f"Sent: {_hdr_dt(sent2, t2, ystyle)}", f"Subject: RE: {topic}", "",
              f"Hi {_first(org)}, {r.choice(CONFLICTS)} - could we move it?", "", _first(requester)]
        m3 = [f"From: {org}", f"Sent: {_hdr_dt(sent3, t3, ystyle)}", f"Subject: RE: {topic}", "",
              f"No problem. Let's move it to {when} at {T(n_start)}, {place}, {length}."]
        if added:
            m3.append(f"I've also added {added} to the invite.")
        m3 += ["", _first(org)]
        msgs = [m1, m2, m3]
        if r.random() < 0.5:
            other = atts[1]
            m4 = [f"From: {other}", f"Sent: {_hdr_dt(sent3, t3 + r.randint(5, 40), ystyle)}",
                  f"Subject: RE: {topic}", "", r.choice(("Works for me.", "Fine by me, see you then.")), _first(other)]
            msgs.append(m4)
        if r.random() < 0.5:
            msgs.reverse()
        doc.state = "\n\n-----\n".join("\n".join(m) for m in msgs)
    else:
        noyear = r.random() < 0.4
        Dn = (lambda d: fdate(d, "wd_dm")) if noyear else (lambda d: fdate(d, "wd_long"))
        if noyear:
            doc.reference_date = sent3
        out = [f"Updated invitation: {topic}", f"Updated by {org} on {fdate(sent3, ystyle)}", "",
               f"When: {Dn(new_day)}, {T(n_start)} - {T(n_start + new_dur)}",
               f"Previously: {Dn(orig_day)}, {T(o_start)} - {T(o_start + dur)}",
               f"Where: {final_room if not video else 'Video call (join link below)'}",
               f"Organizer: {org}", "Attendees: " + "; ".join(atts + ([added] if added else []))]
        if optional:
            out.append("Optional: " + "; ".join(optional))
        agenda = r.sample(("Status of open actions", "Numbers for the period", "Risks and blockers",
                           "Decisions needed", "Timeline check", "Any other business"), 3)
        out += ["", "Agenda:"] + [f"  {i + 1}. {a}" for i, a in enumerate(agenda)]
        out += ["", f"Message from {_first(org)}: moving this at {requester}'s request. "
                + (f"I've added {added}. " if added else "")
                + ("Agenda unchanged." if new_dur == dur else "Shortened agenda." if new_dur < dur else "Extended agenda."),
                "", "Join online: https://meet.example/" + code(r, "***-****-***") if video else "",
                "Reply Yes / No / Maybe"]
        doc.state = "\n".join(x for x in out if x is not None)
        if video:
            room = "Video call"
            final_room = room

    invitees = atts + ([added] if added else [])
    doc.text("meeting_title", topic)
    doc.text("organizer", org)
    doc.items("attendees", invitees, "text", w=2,
              instr="Required invitees of the final meeting, not counting the organizer"
              + (" or optional attendees" if optional else ""))
    if layout == "invite":
        doc.items("optional_attendees", optional, "text", instr="Optional attendees")
    doc.text("requested_by", requester, instr="Person who asked to move the meeting")
    doc.datetime("final_start", new_day, n_start, w=3, instr="Start of the meeting after rescheduling")
    doc.datetime("original_start", orig_day, o_start, w=1.2, instr="Start of the meeting as first scheduled")
    doc.date("final_date", new_day, w=1.2, instr="Date of the rescheduled meeting")
    doc.time("final_start_time", n_start, instr="Start time of the rescheduled meeting")
    doc.time("final_end_time", n_start + new_dur, w=1.5, instr="End time of the rescheduled meeting")
    doc.duration("duration", new_dur, "minutes", integer=True, w=1.5,
                 instr="Length of the rescheduled meeting")
    doc.text("location", final_room, w=1.2, instr="Where the rescheduled meeting takes place")
    doc.text("dial_in_number", None, instr="Phone dial-in number")
    if not video:
        doc.text("meeting_passcode", None, instr="Passcode to join")
    doc.text("agenda_link", None, w=0.6, instr="Link to the agenda document")
    return doc


# ================================================================ support ticket thread

PRODUCTS = (("X2 router", "drops the Wi-Fi connection every few hours"),
            ("Cloud Backup", "fails every nightly backup with error 0x41"),
            ("POS terminal T7", "freezes when printing receipts"),
            ("smart thermostat", "shows the wrong room temperature"),
            ("label printer QL-40", "prints blank labels"),
            ("payroll app", "will not export the monthly report"))


def support_ticket(r: random.Random, layout: str) -> Doc:
    doc = Doc(r, "support_ticket", layout)
    vendor = doc.stem()
    prod_name, issue = r.choice(PRODUCTS)
    product = f"{vendor} {prod_name}"
    cust = doc.person()
    cust_co, cust_co_short = doc.company(("Logistics", "Foods", "Retail", "Dental", "Bakery"))
    agent, agent2 = doc.person(), doc.person()
    escalate = r.random() < 0.4
    tid = r.choice((code(r, "#######"), f"SUP-{code(r, '####-#####')}", code(r, "CS-######")))
    d0 = rand_date(r)
    opened = rand_minutes(r, "08:00", "15:00", 1)
    first = opened + r.randint(6, 290)
    priority = r.choice(("Low", "Normal", "High", "Urgent"))
    order_no = code(r, "#######") if r.random() < 0.6 else None
    serial = code(r, "SN@@########") if r.random() < 0.5 else None
    call = r.random() < 0.55
    call_s = r.randint(95, 2400)
    call_at = first + r.randint(20, 200)
    resolved = r.random() < 0.6
    res_day = d0 + DAY * r.randint(0, 3)
    res_min = rand_minutes(r, "09:00", "17:30", 1)
    if res_day == d0:
        res_min = max(res_min, call_at + 30, first + 30)
    rma = code(r, "RMA-######") if (resolved and r.random() < 0.5) else None
    phone = code(r, "555-01##") if r.random() < 0.3 else None
    call_txt = r.choice((f"{call_s // 60}:{call_s % 60:02d}", f"{call_s // 60} min {call_s % 60} s"))
    ystyle = r.choice(("iso", "dmy", "mdy"))
    tstyle = "24" if layout == "log" else r.choice(("12", "24"))
    T = lambda m: ftime(m, tstyle)
    stamp = lambda d, m: f"{fdate(d, ystyle)} {T(m)}"

    entries = []
    ref = (f" Order {order_no}." if order_no else "") + (f" Serial {serial}." if serial else "")
    entries.append((d0, opened, f"{cust} (customer)",
                    f"Our {product} {issue}, on and off for a while now.{ref}"
                    + (f" Call me on {phone}." if phone else "")))
    entries.append((d0, first, f"{agent} (agent)",
                    r.choice(("Thanks for reporting this. Could you send a photo of the settings screen?",
                              "Sorry for the trouble. Can you confirm the firmware version?",
                              "Thanks - I'm looking into it now. Have you restarted the device since?"))))
    if call:
        who = agent2 if escalate else agent
        entries.append((d0, call_at, f"{who} (agent)",
                        f"Phone call with {_first(cust)}, duration {call_txt}. Walked through a reset."))
    elif escalate:
        entries.append((d0, first + r.randint(20, 200), f"{agent2} (agent)",
                        "Escalated to tier 2; picking this up."))
    if resolved:
        fix = (f"Replacement approved under {rma}; a new unit is on its way." if rma else
               "Firmware update fixed it; customer confirmed.")
        entries.append((res_day, res_min, f"{(agent2 if escalate else agent)} (agent)",
                        f"{fix} Marked resolved."))
        status = "Resolved"
    else:
        entries.append((d0 + DAY, rand_minutes(r, "07:30", "08:55", 1), f"{cust} (customer)",
                        r.choice(("It happened again.", "No change on our side yet.",
                                  "Still the same problem, I'm afraid."))))
        status = r.choice(("Open - waiting on customer", "Open", "Pending"))
        if r.random() < 0.5:
            entries.append((d0 + DAY, rand_minutes(r, "09:00", "12:00", 1), f"{agent} (agent)",
                            "We may need to replace the unit; an RMA will be issued once the return is approved."))
    entries.sort(key=lambda e: (e[0], e[1]))

    if layout == "log":
        out = [f"Ticket {tid} - {product}: {issue}",
               f"Status: {status} | Priority: {priority} | Channel: web form",
               f"Requester: {cust}, {cust_co}", f"Created: {stamp(d0, opened)}", ""]
        for d, m, who, text in entries:
            out.append(f"[{stamp(d, m)}] {who}: {text}")
        doc.state = "\n".join(out)
    else:
        msgs = []
        for d, m, who, text in entries:
            name = who.rsplit(" (", 1)[0]
            msgs.append("\n".join([f"From: {name}", f"Date: {stamp(d, m)}",
                                   f"Subject: [{tid}] {product}" if who.endswith("(customer)") or len(msgs) == 0
                                   else f"Subject: RE: [{tid}] {product}", "", text]))
        head = (f"Ticket {tid} | Priority {priority} | Status {status}\n"
                f"Customer: {cust} ({cust_co})")
        doc.state = head + "\n\n" + "\n\n---\n".join(reversed(msgs) if r.random() < 0.5 else msgs)

    doc.text("ticket_id", tid, w=2)
    doc.text("customer_name", cust)
    doc.text("customer_company", cust_co, alts=[cust_co_short])
    doc.text("product", product, instr="Product the ticket is about")
    doc.text("priority", priority)
    doc.text("first_agent", agent, w=1.2, instr="Support agent who replied first")
    doc.datetime("opened_at", d0, opened, w=1.2, instr="When the ticket was opened")
    doc.duration("first_response_minutes", first - opened, "minutes", integer=True, w=2,
                 instr="Minutes from the ticket being opened to the first agent reply")
    doc.datetime("resolved_at", res_day if resolved else None, res_min, w=1.5,
                 instr="When the ticket was marked resolved")
    if call:
        doc.duration("call_duration", call_s, "seconds", integer=True, w=1.5, instr="Length of the phone call")
    doc.text("order_number", order_no, instr="Customer's order number")
    doc.text("serial_number", serial, instr="Serial number of the device")
    doc.text("rma_number", rma, w=1.2, instr="Return authorisation (RMA) number")
    doc.text("customer_phone", phone, instr="Customer's phone number")
    doc.text("customer_email", None, w=0.6, instr="Customer's email address")
    doc.number("satisfaction_score", None, instr="Customer satisfaction rating given for the ticket")
    return doc


# ================================================================ maintenance / service log

TASKS = {
    "vehicle": ("Oil and filter change", "Brake pads replaced (front)", "Tyre rotation", "Coolant flush",
                "Wiper blades replaced", "Battery test", "Cabin air filter replaced", "Wheel alignment"),
    "forklift": ("Hydraulic fluid top-up", "Mast chain lubrication", "Battery water check",
                 "Brake shoes replaced", "Fork wear check", "Tyre replacement (rear)", "Seat belt switch replaced"),
}
LABOUR_ONLY = {"vehicle": ("Tyre rotation", "Battery test", "Wheel alignment"),
               "forklift": ("Battery water check", "Fork wear check")}
# (part number, description, the task it belongs to)
PARTS = {
    "vehicle": (("OF-2210", "Oil filter", "Oil and filter change"),
                ("EO-5W30", "Engine oil 5W-30, 5 L", "Oil and filter change"),
                ("BP-118", "Front brake pads", "Brake pads replaced (front)"),
                ("WB-24", "Wiper blade 24in", "Wiper blades replaced"),
                ("CF-77", "Cabin air filter", "Cabin air filter replaced"),
                ("CL-05", "Coolant 5 L", "Coolant flush")),
    "forklift": (("HF-46", "Hydraulic fluid 20 L", "Hydraulic fluid top-up"),
                 ("CH-08", "Chain lubricant", "Mast chain lubrication"),
                 ("TR-1840", "Solid tyre 18x7", "Tyre replacement (rear)"),
                 ("SB-12", "Seat belt switch", "Seat belt switch replaced"),
                 ("BK-33", "Brake shoe set", "Brake shoes replaced")),
}


def maintenance_log(r: random.Random, layout: str) -> Doc:
    doc = Doc(r, "maintenance_log", layout)
    kind = r.choice(("vehicle", "forklift"))
    if kind == "vehicle":
        asset_id = code(r, "FLT-0##")
        asset = f"{r.choice(('Van', 'Truck', 'Pickup'))} {asset_id[-2:]}"
        unit, interval = r.choice((("km", 15000), ("mi", 10000), ("km", 20000)))
        reading = r.randint(12, 180) * 1000 + r.randint(0, 999)
    else:
        asset_id = code(r, "FL-0#")
        asset = f"{r.choice(('Forklift', 'Reach truck', 'Pallet stacker'))} {int(asset_id[-1]) + 1}"
        unit, interval = "hours", r.choice((250, 500))
        reading = r.randint(800, 9000)
    site, _ = doc.company(("Logistics", "Foods", "Distribution"))
    tech = doc.person()
    M = _money(r)
    D, _ = _dates(r, [], None)
    if layout == "workorder":
        wo = code(r, r.choice(("WO-#####", "#######", "SR-####-##")))
        day = rand_date(r, hi=dt.date(2026, 12, 28))
        if day.day > 28:
            day = day.replace(day=28)
        picked = r.sample(PARTS[kind], r.randint(1, 3))
        parts = [(pn, desc, r.randint(1, 4), r.randint(450, 18900)) for pn, desc, _ in picked]
        tasks = list(dict.fromkeys(t for _, _, t in picked)) + r.sample(LABOUR_ONLY[kind], r.randint(0, 2))
        parts_total = sum(q * u for _, _, q, u in parts)
        lab_h = r.choice((0.5, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 3.75, 4.0))
        rate = r.choice((7500, 8500, 9500, 11000, 12500))
        labour = round(lab_h * rate)
        total = parts_total + labour
        print_total = r.random() < 0.5
        by_date = r.random() < 0.5
        months = r.choice((3, 6, 12))
        next_date = add_months(day, months)
        print_next_date = by_date and r.random() < 0.5
        warranty = r.choice((("months", 12), ("months", 6), ("days", 90), None))
        out = [f"WORK ORDER {wo}", f"Date: {D(day)}", f"Customer: {site}", f"Asset: {asset} ({asset_id})",
               f"{'Odometer' if kind == 'vehicle' else 'Hour meter'}: {reading:,} {unit}",
               f"Technician: {tech}", "", "Work performed:"] + [f"- {t}" for t in tasks] + ["", "Parts:"]
        for pn, desc, q, u in parts:
            out.append(f"  {pn.ljust(9)}{desc.ljust(24)}x{q}  {M(q * u)}")
        out += ["", f"Labour: {lab_h:g} h @ {M(rate)}/h = {M(labour)}", f"Parts total: {M(parts_total)}"]
        if print_total:
            out.append(f"Total: {M(total)}")
        out.append(f"Service interval: every {interval:,} {unit}" + (f" or {months} months" if by_date else ""))
        if print_next_date:
            out.append(f"Next service due: {D(next_date)}")
        if warranty:
            out.append(f"Parts warranty: {warranty[1]} {warranty[0]}")
        out += ["", "Signed off by the technician. Thank you."]
        doc.state = "\n".join(out)

        doc.text("work_order_number", wo, w=1.5)
        doc.text("asset_id", asset_id)
        doc.date("service_date", day)
        doc.text("technician", tech)
        doc.number("meter_reading", reading, integer=True, unit=unit, instr="Odometer or hour meter reading")
        doc.duration("labour_hours", lab_h, "hours", decimals=2, instr="Labour time charged")
        doc.money("labour_cost", labour)
        doc.items("parts_used", [p[1] for p in parts], "text", instr="Descriptions of the parts used")
        doc.items("part_numbers", [p[0] for p in parts], "text", w=0.7, instr="Part numbers used")
        doc.money("parts_total", parts_total)
        doc.money("total_cost", total, w=2, instr="Total cost of the work order: parts total plus labour")
        doc.number("next_service_reading", reading + interval, integer=True, unit=unit, w=2,
                   instr="Meter reading at which the next service is due: current reading plus the service interval")
        doc.date("next_service_date", next_date if by_date else None, w=1.5,
                 instr="Date the next service is due (service date plus the interval in months)")
        if warranty:
            doc.duration("parts_warranty", warranty[1], warranty[0], integer=True, instr="Warranty period on parts")
        else:
            doc.duration("parts_warranty", None, "months", instr="Warranty period on parts")
        doc.text("customer_po", None, instr="Customer purchase order number")
        doc.duration("downtime_hours", None, "hours", w=0.7, instr="Hours the asset was out of service")
        return doc

    # history log
    n = r.randint(3, 5)
    day = rand_date(r, lo=dt.date(2025, 6, 1))
    rows = []
    rd = reading + interval * n
    history_tasks = r.sample(TASKS[kind], n)
    for i in range(n):
        cost = r.randint(4000, 90000)
        task = history_tasks[i]
        rows.append((day, rd, task, tech if i % 2 == 0 or r.random() < 0.5 else None, cost))
        day -= DAY * r.randint(40, 120)
        rd -= r.randint(int(interval * 0.7), interval)
    techs = [doc.person()]
    rows = [(d, m, t, w or techs[0], c) for d, m, t, w, c in rows]
    newest_first = r.random() < 0.5
    shown = rows if newest_first else list(reversed(rows))
    last = rows[0]
    prev = rows[1]
    next_due = last[1] + interval
    out = [f"Maintenance history - {asset} ({asset_id})", f"Site: {site}",
           f"Interval: every {interval:,} {unit}", ""]
    tbl = [("Date", "Meter", "Work done", "Technician", "Cost")]
    tbl += [(D(d), f"{m:,} {unit}", t, w, M(c)) for d, m, t, w, c in shown]
    widths = [max(len(x[k]) for x in tbl) for k in range(5)]
    out += _pad(tbl, widths, "lrllr")
    out += ["", f"Next service due at {next_due:,} {unit}.",
            "Report any warning lights, leaks or unusual noises to the workshop before use."]
    doc.state = "\n".join(out)

    doc.text("asset_id", asset_id)
    doc.date("last_service_date", last[0], w=2, instr="Date of the most recent service")
    doc.items("service_dates", [x[0] for x in rows], "date", w=1.5, instr="Dates of all service entries")
    doc.money("last_service_cost", last[4], w=1.5, instr="Cost of the most recent service")
    doc.number("last_meter_reading", last[1], integer=True, unit=unit, instr="Meter reading at the most recent service")
    doc.number("usage_between_services", last[1] - prev[1], integer=True, unit=unit, w=1.5,
               instr="Meter difference between the two most recent services")
    doc.text("last_technician", last[3], instr="Technician on the most recent service")
    doc.text("last_work_done", last[2], instr="Work done at the most recent service")
    doc.number("service_count", n, integer=True, instr="Number of service entries")
    doc.number("next_service_reading", next_due, integer=True, unit=unit, instr="Meter reading when the next service is due")
    doc.date("next_service_date", None, w=1.2, instr="Date the next service is due")
    doc.duration("parts_warranty", None, "months", instr="Warranty period on parts")
    doc.text("work_order_number", None, instr="Work order number of the most recent service")
    return doc


# ================================================================ payslip

def payslip(r: random.Random, layout: str) -> Doc:
    doc = Doc(r, "payslip", layout)
    employer, employer_short = doc.company(("Logistics", "Foods", "Health", "Engineering", "Hospitality"))
    emp = doc.person()
    emp_id = code(r, r.choice(("#####", "E-####", "PY####")))
    cur = r.choice(("USD", "USD", "GBP", "EUR"))
    M = _money(r, cur)
    monthly = r.random() < 0.5
    if monthly:
        y, mo = r.choice((2025, 2026)), r.randint(1, 12)
        p0 = dt.date(y, mo, 1)
        p1 = dt.date(y + (mo == 12), mo % 12 + 1, 1) - DAY
        idx = mo
    else:
        p0 = rand_date(r)
        p0 -= DAY * p0.weekday()  # a Monday
        p1 = p0 + DAY * 13
        idx = max(1, (p0 - dt.date(p0.year, 1, 1)).days // 14 + 1)
    pay = p1 + DAY * r.randint(0, 5)
    hourly = r.random() < 0.55
    earn = []  # (label, hours or None, rate or None, cents)
    if hourly:
        hours = r.choice((160, 168, 172.5, 176)) if monthly else r.choice((70, 72, 75, 76.5, 80))
        rate = r.randint(1850, 5200)
        earn.append(("Regular pay", hours, rate, round(hours * rate)))
        ot = r.choice((0, 0, 2.5, 4, 6, 7.5, 10)) if r.random() < 0.6 else 0
        if ot:
            earn.append(("Overtime (1.5x)", ot, round(rate * 1.5), round(ot * round(rate * 1.5))))
    else:
        base = r.randint(3200, 9800) * 100 if monthly else r.randint(1500, 4500) * 100
        earn.append(("Base salary", None, None, base))
        hours = ot = None
    if r.random() < 0.2:
        earn.append(("Bonus", None, None, r.randint(10, 200) * 1000))
    gross = sum(e[3] for e in earn)
    deds = [("Income tax", pct_of(gross, r.randint(1100, 2200))),
            ("Social insurance", pct_of(gross, r.choice((620, 765, 800)))),
            ]
    pension = r.choice((3, 4, 5, 6))
    deds.append((f"Pension ({pension}%)", pct_of(gross, pension * 100)))
    if r.random() < 0.6:
        deds.append(("Health plan", r.randint(45, 180) * 100))
    total_ded = sum(d[1] for d in deds)
    net = gross - total_ded
    ytd = gross * idx + r.randint(0, 3) * 10000
    acct = code(r, "####") if r.random() < 0.4 else None
    tax_code = code(r, "####@") if r.random() < 0.3 else None
    D, _ = _dates(r, [], None)

    if layout == "table":
        out = [f"{employer} - Payslip", "", f"Employee: {emp}    ID: {emp_id}",
               f"Pay period: {D(p0)} to {D(p1)}    Pay date: {D(pay)}"]
        if tax_code:
            out.append(f"Tax code: {tax_code}")
        out.append("")
        rows = [("Earnings", "Hours", "Rate", "Amount")]
        for lab, h, rt, c in earn:
            rows.append((lab, f"{h:g}" if h else "", fnum(rt) if rt else "", fnum(c)))
        rows.append(("Gross pay", "", "", fnum(gross)))
        out += _pad(rows, (18, 6, 8, 11), "lrrr")
        out.append("")
        drows = [("Deductions", "", "", "Amount")] + [(lab, "", "", fnum(c)) for lab, c in deds]
        drows.append(("Total deductions", "", "", fnum(total_ded)))
        out += _pad(drows, (18, 6, 8, 11), "lrrr")
        out += ["", f"NET PAY ({cur}): {fnum(net)}", f"Year to date: gross {fnum(ytd)}"]
        if acct:
            out.append(f"Paid by bank transfer to account ending {acct}.")
    else:
        out = [f"PAYSLIP | {employer}", f"{doc.street()}, {doc.city()[0]}", "",
               f"Name: {emp}", f"Employee no.: {emp_id}",
               f"Pay frequency: {'monthly' if monthly else 'every two weeks'}",
               f"Period: {D(p0)} - {D(p1)}", f"Paid on: {D(pay)}", "", "Earnings"]
        for lab, h, rt, c in earn:
            extra = f" ({h:g} h at {M(rt)})" if h else ""
            out.append(f"{lab}{extra}: {M(c)}")
        out += [f"Gross pay: {M(gross)}", "", "Deductions"] + [f"{lab}: -{M(c)}" for lab, c in deds]
        out += ["", f"Net pay: {M(net)}", f"Gross pay year to date: {M(ytd)}"]
        if tax_code:
            out.append(f"Tax code: {tax_code}")
        if acct:
            out.append(f"Net pay sent to account ending {acct}.")
        out += ["", "This payslip is confidential. Questions about your pay? Contact the payroll team",
                "through the staff portal; please keep this document for your records."]
    doc.state = "\n".join(out)

    doc.text("employer", employer, alts=[employer_short])
    doc.text("employee_name", emp)
    doc.text("employee_id", emp_id)
    doc.date("pay_date", pay, w=1.5, instr="Date the employee is paid")
    doc.date("period_start", p0, instr="First day of the pay period")
    doc.date("period_end", p1, instr="Last day of the pay period")
    doc.money("gross_pay", gross, cur, w=1.5, instr="Gross pay for this period")
    doc.money("net_pay", net, cur, w=2, instr="Net (take-home) pay for this period")
    doc.money("total_deductions", total_ded, cur, w=2, instr="Sum of all deductions (gross pay minus net pay)")
    doc.money("income_tax", deds[0][1], cur)
    doc.money_items("deduction_amounts", [d[1] for d in deds], cur, instr="Amount of each deduction, in payslip order")
    doc.money("ytd_gross", ytd, cur, w=1.2, instr="Year-to-date gross pay")
    if hourly:
        doc.duration("regular_hours", hours, "hours", decimals=2, instr="Regular hours paid this period")
        doc.number("hourly_rate", amount(earn[0][2]), decimals=2, unit=cur, instr="Regular hourly rate")
        if ot:
            doc.duration("overtime_hours", ot, "hours", decimals=2, w=1.2)
            doc.money("overtime_pay", earn[1][3], cur)
    doc.text("bank_account_last_four", acct, instr="Last four digits of the account the pay goes to")
    doc.text("tax_code", tax_code)
    doc.date("next_pay_date", None, instr="Date of the next payment")
    doc.text("national_insurance_number", None, w=0.6, instr="Employee's national insurance or social security number")
    return doc


# ================================================================ purchase order

PO_LINES = (("HB-M840", "Hex bolts M8x40 (box of 100)"), ("BR-6204", "Bearing 6204-2RS"),
            ("SG-L", "Safety gloves, size L (pair)"), ("CT-300", "Cable ties 300mm (pack of 100)"),
            ("PW-500", "Pallet wrap 500mm roll"), ("AF-2025", "Air filter 20x25x1"),
            ("DB-B42", "Drive belt B42"), ("GC-400", "Grease cartridge 400g"),
            ("CB-403", "Corrugated boxes 40x30x30 (25)"), ("LT-12", "Label tape 12mm"),
            ("SH-300", "Shelf bracket 300mm"), ("TP-48", "Packing tape 48mm (6 rolls)"))


def purchase_order(r: random.Random, layout: str) -> Doc:
    doc = Doc(r, "purchase_order", layout)
    buyer, buyer_short = doc.company(("Logistics", "Foods", "Retail", "Manufacturing", "Health"))
    supplier, supplier_short = doc.company(("Supply", "Industrial", "Components", "Wholesale"))
    contact, approver, sup_contact = doc.person(), doc.person(), doc.person()
    hq, _ = doc.city()
    wh_city, _ = doc.city(avoid=[hq])
    M = _money(r)
    po_date = rand_date(r)
    while po_date.weekday() > 4:
        po_date += DAY
    po_no = r.choice((f"PO-{po_date.year}-{code(r, '####')}", code(r, "PO######"), code(r, "4500######")))
    rel = None
    if layout == "email" and r.random() < 0.5:
        rel, req = rel_day(r, po_date)
        if (req - po_date).days < 2:
            rel, req = None, po_date + DAY * r.randint(7, 30)
    else:
        req = po_date + DAY * r.randint(5, 35)
    lines = [(sku, desc, r.choice((2, 5, 10, 12, 20, 24, 50, 100)), r.randint(120, 9500))
             for sku, desc in r.sample(PO_LINES, r.randint(2, 5))]
    subtotal = sum(q * u for _, _, q, u in lines)
    freight = r.choice((0, 2500, 4500, 8000, 12500))
    total = subtotal + freight
    net = r.choice((30, 30, 45, 60))
    approved = layout == "table" and r.random() < 0.7
    quote = code(r, "Q-#####") if r.random() < 0.5 else None
    D, noyear = _dates(r, [po_date, req], po_date, 0.4)
    if noyear or rel:
        doc.reference_date = po_date
    when = rel if rel else D(req)

    if layout == "table":
        out = ["PURCHASE ORDER", f"{buyer}, {doc.street()}, {hq}", "", f"PO number: {po_no}",
               f"PO date: {D(po_date)}", f"Supplier: {supplier}", f"Supplier contact: {sup_contact}",
               f"Ship to: {buyer_short} warehouse, {doc.street()}, {wh_city}",
               f"Deliver by: {D(req)}", f"Payment terms: Net {net}",
               f"Supplier quote: {quote}" if quote else r.choice(("Supplier quote: to follow", "")),
               f"Requested by: {contact}",
               f"Approved by: {approver}" if approved else "Approval: pending", ""]
        dw = max(len(x[1]) for x in lines) + 1
        rows = [("Line", "SKU", "Description", "Qty", "Unit price", "Line total")]
        rows += [(str(i + 1), s, d, str(q), M(u), M(q * u)) for i, (s, d, q, u) in enumerate(lines)]
        out += _pad(rows, (4, 8, dw, 4, 11, 12), "lllrrr")
        out += ["", f"Subtotal: {M(subtotal)}", f"Freight: {M(freight)}", f"Order total: {M(total)}", "",
                "Please quote the PO number on all invoices and delivery notes."]
        doc.state = "\n".join(x for x in out if x is not None)
    else:
        out = [f"From: {contact} <{_email(contact, buyer_short)}>", f"To: {sup_contact} <{_email(sup_contact, supplier_short)}>",
               f"Date: {D(po_date)}", f"Subject: Purchase order {po_no} for {supplier}", "", f"Hi {_first(sup_contact)},", "",
               f"Please supply the following against PO {po_no}:", ""]
        for s, d, q, u in lines:
            out.append(f"- {q} x {d} (SKU {s}) at {M(u)} each = {M(q * u)}")
        out += ["", f"Subtotal: {M(subtotal)}. Freight as quoted: {M(freight)}.",
                f"Please deliver to our warehouse at {doc.street()}, {wh_city} by {when}.",
                f"Our usual terms apply: net {net} days from invoice."]
        out.append(f"This order follows your quote {quote}." if quote else
                   r.choice(("Please send your quote reference when you confirm.", "")))
        out += ["", "Thanks,", contact, f"Purchasing, {buyer}", f"{hq}"]
        doc.state = "\n".join(x for x in out if x is not None)

    doc.text("po_number", po_no, w=2)
    doc.text("buyer_company", buyer, alts=[buyer_short], instr="Company placing the order")
    doc.text("supplier_name", supplier, alts=[supplier_short])
    doc.date("order_date", po_date, instr="Date of the purchase order")
    doc.date("requested_delivery_date", req, w=2, instr="Date the goods are needed by")
    doc.duration("lead_time_days", (req - po_date).days, "days", integer=True, w=1.5,
                 instr="Days from the order date to the requested delivery date")
    doc.text("ship_to_city", wh_city, w=1.2, instr="City of the delivery address")
    doc.items("item_descriptions", [x[1] for x in lines], "text", instr="Description of each line")
    doc.items("skus", [x[0] for x in lines], "text", instr="SKU of each line, in order")
    doc.items("quantities", [x[2] for x in lines], "number", decimals=0, instr="Quantity of each line, in order")
    doc.money("order_total", total, w=2, instr="Total order value: subtotal plus freight")
    doc.money("freight", freight, instr="Freight charge")
    doc.duration("payment_terms", net, "days", integer=True, instr="Net payment term")
    doc.text("requested_by", contact, instr="Person at the buyer who placed the order")
    doc.text("approved_by", approver if approved else None, instr="Person who approved the purchase order")
    doc.text("quote_reference", quote, w=1.2, instr="Supplier quote reference")
    doc.text("contract_number", None, instr="Framework contract number")
    doc.text("incoterms", None, w=0.6, instr="Incoterms delivery term")
    return doc


# ================================================================ utility bill

def utility_bill(r: random.Random, layout: str) -> Doc:
    doc = Doc(r, "utility_bill", layout)
    kind = r.choice(("electric", "electric", "gas", "water"))
    stem = doc.stem()
    utility = f"{stem} {dict(electric='Energy', gas='Gas', water='Water')[kind]}"
    unit, (ulo, uhi), (rlo, rhi) = {"electric": ("kWh", (180, 1400), (1180, 3120)),
                                    "gas": ("therms", (12, 160), (9000, 18000)),
                                    "water": ("m3", (6, 40), (21000, 48000))}[kind]
    cust = doc.person()
    acct = code(r, r.choice(("####-####-##", "##########", "@@-#######")))
    meter = code(r, "########") if r.random() < 0.6 else None
    start = rand_date(r)
    days = r.randint(29, 33)
    end = start + DAY * (days - 1)
    bill = end + DAY * r.randint(1, 3)
    due = bill + DAY * r.randint(14, 25)
    usage = r.randint(ulo, uhi)
    prev_read = r.randint(1000, 90000)
    cur_read = prev_read + usage
    rate = r.randint(rlo, rhi)  # 1/10000 of a currency unit per unit
    energy = (usage * rate + 50) // 100
    fixed = r.randint(900, 2500)
    taxes = pct_of(energy + fixed, r.choice((300, 500, 650, 800)))
    current = energy + fixed + taxes
    prev_bal = r.randint(3000, 30000) if r.random() < 0.7 else 0
    paid = prev_bal if (prev_bal and r.random() < 0.75) else (prev_bal // 2 if prev_bal else 0)
    pay_date = end - DAY * r.randint(2, 20) if paid else None
    amount_due = prev_bal - paid + current
    M = _money(r)
    D, noyear = _dates(r, [start, end, bill, due] + ([pay_date] if pay_date else []), bill, 0.3)
    if noyear:
        doc.reference_date = bill
    rate_txt = f"{rate / 10000:.4f}"
    addr = f"{doc.street()}, {doc.city()[0]}"

    if layout == "kv":
        out = [f"{utility} - {kind.title()} bill", "", f"Account number: {acct}", f"Customer: {cust}",
               f"Service address: {addr}", f"Bill date: {D(bill)}",
               f"Billing period: {D(start)} to {D(end)} ({days} days)"]
        if meter:
            out.append(f"Meter number: {meter}")
        out += [f"Previous reading: {prev_read:,}", f"Current reading: {cur_read:,}", "",
                "Account summary", f"Previous balance: {M(prev_bal)}"]
        if paid:
            out.append(f"Payment received {D(pay_date)}: -{M(paid)}")
        out += [f"Balance forward: {M(prev_bal - paid)}", "", "Current charges",
                f"{kind.title()} usage at ${rate_txt} per {unit}: {M(energy)}",
                f"Service charge: {M(fixed)}", f"Taxes: {M(taxes)}", f"Total current charges: {M(current)}", "",
                f"AMOUNT DUE: {M(amount_due)}", f"Due date: {D(due)}", "",
                "Pay online, by phone or by mail. Late payments may incur a fee."]
    else:
        out = [f"From: {utility} <billing@{slug(stem)}.example>", f"Date: {D(bill)}",
               f"Subject: Your {utility} bill is ready", "", f"Hi {_first(cust)},", "",
               f"Your bill for account {acct} ({cust}, {addr}) is ready.",
               f"Amount due: {M(amount_due)}, due by {D(due)}.", "",
               f"Between {D(start)} and {D(end)} you used {usage:,} {unit}, charged at ${rate_txt} per {unit}.",
               f"This period's charges come to {M(current)}, including a service charge of {M(fixed)} and taxes of {M(taxes)}."]
        if prev_bal:
            out.append(f"Your previous balance was {M(prev_bal)}"
                       + (f"; thanks for your payment of {M(paid)} on {D(pay_date)}." if paid else "."))
        else:
            out.append("There is no balance carried forward from your previous bill.")
        if meter:
            out.append(f"Meter {meter} was read on {D(end)}.")
        out += ["", "View the full bill and payment options in your online account.", f"- {utility}"]
    doc.state = "\n".join(out)

    doc.text("account_number", acct, w=1.2)
    doc.text("customer_name", cust)
    doc.money("amount_due", amount_due, w=3, instr="Total amount due, including any balance carried forward")
    doc.date("due_date", due, w=2)
    doc.number("usage", usage, integer=True, unit=unit, w=2,
               instr="Consumption in the billing period (current minus previous meter reading)")
    doc.date("billing_start", start, instr="First day of the billing period")
    doc.date("billing_end", end, instr="Last day of the billing period")
    doc.money("current_charges", current, w=1.5, instr="Charges for this billing period only")
    doc.money("previous_balance", prev_bal)
    doc.number("unit_rate", rate / 10000, decimals=4, unit=f"USD/{unit}", instr=f"Price per {unit}")
    if paid:
        doc.money("last_payment_amount", paid, instr="Amount of the last payment received")
    doc.date("last_payment_date", pay_date, instr="Date the last payment was received")
    doc.text("meter_number", meter)
    doc.number("previous_reading", prev_read if layout == "kv" else None, integer=True,
               instr="Previous meter reading")
    doc.date("autopay_date", None, instr="Date the automatic payment will be taken")
    doc.text("tariff_name", None, w=0.7, instr="Name of the tariff or rate plan")
    return doc


# ================================================================ lease summary

def lease_summary(r: random.Random, layout: str) -> Doc:
    doc = Doc(r, "lease_summary", layout)
    landlord, landlord_short = doc.company(("Property Management", "Properties", "Estates", "Realty"))
    commercial = r.random() < 0.3
    if commercial:
        tenant, tenant_short = doc.company(("Studio", "Dental", "Bakery", "Analytics"))
        unit_txt = f"Suite {r.randint(1, 4)}{r.randint(0, 2)}{r.randint(1, 9)}"
    else:
        tenant = tenant_short = doc.person()
        unit_txt = f"Apt {r.randint(1, 12)}{r.choice('ABCD')}"
    premises = f"{doc.street()}, {unit_txt}"
    city = doc.city()[0]
    y, mo = r.choice((2025, 2026, 2026)), r.randint(1, 12)
    start = dt.date(y, mo, 1)
    term = r.choice((6, 12, 12, 18, 24, 36))
    end = add_months(start, term) - DAY
    in_years = term % 12 == 0 and r.random() < 0.5
    term_txt = (f"{number_word(term // 12)} ({term // 12}) year{'s' if term > 12 else ''}" if in_years
                else f"{term} months")
    ask_unit = r.choice(("months", "years")) if term % 12 == 0 else "months"
    term_val = term if ask_unit == "months" else term // 12
    rent = r.randint(95, 480) * 1000 if not commercial else r.randint(180, 900) * 1000
    dep_mult = r.choice((1, 1.5, 2))
    deposit = round(rent * dep_mult)
    late = r.choice((5000, 7500, 10000, 15000)) if r.random() < 0.65 else None
    notice_unit, notice = r.choice((("days", 30), ("days", 60), ("days", 90), ("weeks", 4), ("weeks", 8)))
    schedule = [add_months(start, k) for k in range(3)] if r.random() < 0.7 else None
    review = add_months(start, 12) if (term > 12 and r.random() < 0.5) else None
    inc = r.choice((2, 3, 3.5, 4)) if review else None
    parking = f"P-{r.randint(1, 60)}" if r.random() < 0.4 else None
    guarantor = doc.person() if (not commercial and r.random() < 0.3) else None
    M = _money(r)
    D, _ = _dates(r, [], None)

    if layout == "abstract":
        out = ["LEASE ABSTRACT", "", f"Landlord: {landlord}", f"Tenant: {tenant}", f"Premises: {premises}, {city}",
               f"Commencement date: {D(start)}", f"Expiry date: {D(end)}", f"Term: {term_txt}",
               f"Monthly rent: {M(rent)}, due on the 1st of each month",
               f"Security deposit: {M(deposit)}",
               f"Late fee: {M(late)} if rent is more than 5 days late" if late else "Late fee: per statute",
               f"Notice to vacate: {notice} {notice_unit} in writing"]
        if schedule:
            out.append("First rent payments due: " + ", ".join(D(d) for d in schedule))
        if review:
            out.append(f"Rent review: +{inc:g}% from {D(review)}")
        out.append(f"Parking: space {parking}" if parking else "Parking: none included")
        if guarantor:
            out.append(f"Guarantor: {guarantor}")
        out += ["Utilities: paid by tenant", "", "This abstract is a summary; the signed lease governs."]
    else:
        out = [f"From: {landlord}", f"To: {tenant}", f"Subject: Your lease for {premises}", "",
               f"Dear {(_first(tenant) if not commercial else tenant_short)},", "",
               f"Welcome! This letter summarises the lease between {landlord} and {tenant} for {premises}, {city}.",
               "",
               f"The lease runs for {term_txt}, from {D(start)} to {D(end)}. Rent is {M(rent)} per month, "
               f"payable in advance on the 1st, and we hold a security deposit of {M(deposit)}.",
               (f"A late fee of {M(late)} applies to payments more than five days late. " if late else "")
               + f"Either party must give {notice} {notice_unit}' written notice to end the tenancy."]
        if schedule:
            out.append("Your first three payments are due on " + ", ".join(D(d) for d in schedule[:2])
                       + f" and {D(schedule[2])}.")
        if review:
            out.append(f"The rent goes up by {inc:g}% from {D(review)}.")
        if parking:
            out.append(f"Parking space {parking} is included.")
        if guarantor:
            out.append(f"{guarantor} has signed as guarantor.")
        out += ["", "Kind regards,", doc.person(), f"Lettings team, {landlord_short}"]
    doc.state = "\n".join(out)

    doc.text("landlord", landlord, alts=[landlord_short])
    doc.text("tenant", tenant, alts=[tenant_short] if tenant_short != tenant else None)
    doc.date("lease_start", start, instr="Commencement date of the lease")
    doc.date("lease_end", end, w=2, instr="Last day of the lease")
    doc.duration("lease_term", term_val, ask_unit, integer=True, w=1.5, instr="Length of the lease term")
    doc.money("monthly_rent", rent, w=1.2)
    doc.money("security_deposit", deposit, w=1.5)
    doc.money("annual_rent", rent * 12, w=1.5, instr="Rent for one year: the monthly rent times 12")
    doc.duration("notice_period", notice, notice_unit, integer=True, instr="Notice needed to end the tenancy")
    doc.items("rent_due_dates", schedule, "date", w=1.2, instr="Due dates of the first rent payments listed")
    doc.money("late_fee", late, instr="Fee charged for late rent")
    doc.number("rent_increase_percent", inc, instr="Scheduled rent increase, in percent")
    doc.date("rent_review_date", review, instr="Date the rent increase takes effect")
    doc.text("parking_space", parking, instr="Parking space included with the lease")
    doc.text("guarantor", guarantor)
    doc.date("break_clause_date", None, instr="Earliest date the tenant may break the lease")
    doc.money("pet_deposit", None, instr="Additional deposit for pets")
    return doc


# ================================================================ incident report

SERVICES = ("Payments API", "Customer portal", "Order sync", "Email notifications", "Search",
            "Mobile login", "Reporting dashboard", "Inventory service", "Checkout", "File uploads")
CAUSES = ("an expired TLS certificate on the internal load balancer",
          "a database migration that locked the orders table",
          "a configuration change that cut the connection pool to 5",
          "a full disk on the primary cache node",
          "a bad release that retried failed requests without backoff",
          "a DNS record removed during a cleanup")
FIXES = ("rolled back the release", "failed over to the standby database", "renewed the certificate",
         "restored the configuration", "cleared the disk and restarted the node", "restored the DNS record")


def incident_report(r: random.Random, layout: str) -> Doc:
    doc = Doc(r, "incident_report", layout)
    org = doc.stem()
    inc_id = r.choice((f"INC-{code(r, '####-####')}", code(r, "INC######")))
    sev = r.choice(("SEV-1", "SEV-2", "SEV-2", "SEV-3"))
    cmdr, oncall, owner2 = doc.person(), doc.person(), doc.person()
    svcs = r.sample(SERVICES, r.randint(1, 3))
    title = f"{svcs[0]} errors and timeouts"
    d0 = rand_date(r)
    s = rand_minutes(r, "00:00", "23:00", 1)
    det = s + r.randint(2, 25)
    mit = det + r.randint(10, 120)
    res = mit + r.randint(5, 180)
    ongoing = layout == "update" and r.random() < 0.35
    known_cause = r.random() < 0.65
    ci = r.randrange(len(CAUSES))
    cause, fix = CAUSES[ci], FIXES[ci]
    customers = r.randint(40, 9000) if r.random() < 0.7 else None
    fu = [(r.choice(("Add alerting on certificate expiry", "Add a lock timeout to migrations",
                     "Load-test the connection pool settings", "Add disk usage alerts at 80%",
                     "Require backoff in the client library", "Protect DNS records from bulk edits")),
           cmdr, d0 + DAY * r.randint(5, 20)),
          (r.choice(("Write the customer-facing summary", "Review the on-call runbook",
                     "Schedule a game day for this failure")), owner2, d0 + DAY * r.randint(3, 30))]
    review = (d0 + DAY * r.randint(1, 6), rand_minutes(r, "09:00", "16:00", 30)) if r.random() < 0.5 else None
    D, _ = _dates(r, [], None)

    def at(m: int, with_date: bool = True) -> str:
        d = d0 + DAY * (m // 1440)
        return f"{D(d)} {hhmm(m)} UTC" if with_date else f"{hhmm(m)} UTC"

    cross = res // 1440 > 0 or mit // 1440 > 0 or det // 1440 > 0
    if layout == "report":
        out = [f"Incident report {inc_id}", f"Title: {title}", f"Severity: {sev}", "Status: Resolved",
               f"Incident commander: {cmdr}", "", "Timeline (UTC)",
               f"- {at(s)}  Impact begins: requests to {svcs[0]} start failing",
               f"- {at(det, cross)}  Alert fires; {oncall} is paged",
               f"- {at(mit, cross)}  Mitigation: we {fix}",
               f"- {at(res, cross)}  Resolved: error rates back to normal", "",
               "Affected services: " + ", ".join(svcs),
               f"Customer impact: {customers:,} customers saw failed requests." if customers else
               "Customer impact: number of affected customers still being confirmed.",
               f"Root cause: {cause}." if known_cause else "Root cause: under investigation.", "",
               "Follow-up actions:"]
        out += [f"- {a} (owner {o}, due {D(d)})" for a, o, d in fu]
        if review:
            out.append(f"Post-incident review: {D(review[0])} at {hhmm(review[1])} UTC")
        doc.state = "\n".join(out)
    else:
        ups = [(det + r.randint(3, 12), f"We are investigating errors on {', '.join(svcs)} that began at {at(s)}.")]
        ups.append((mit, f"Mitigation in progress: we {fix}. Error rates are dropping."))
        if not ongoing:
            ups.append((res, "Resolved. Error rates have been back to normal since " + at(res) + "."
                        + (f" Root cause: {cause}." if known_cause else " Root cause: still under investigation.")))
        out = [f"Subject: [{'RESOLVED' if not ongoing else 'ONGOING'}] {inc_id} {title}",
               f"Severity {sev}; incident commander {cmdr}; first alert at {at(det)} (on-call {oncall}).", ""]
        msgs = [f"Update {i + 1} ({at(t)}): {txt}" for i, (t, txt) in enumerate(ups)]
        out += list(reversed(msgs)) if r.random() < 0.5 else msgs
        if customers:
            out += ["", f"Customers affected so far: {customers:,}."]
        out += ["", f"- {org} status team"]
        doc.state = "\n".join(out)

    doc.text("incident_id", inc_id, w=2)
    doc.text("severity", sev)
    doc.text("incident_commander", cmdr)
    doc.datetime("started_at", d0, s, w=2, instr="When the customer impact began")
    doc.datetime("detected_at", d0, det, w=1.2, instr="When the first alert fired")
    doc.datetime("resolved_at", None if ongoing else d0, res, w=1.5, instr="When the incident was resolved")
    doc.duration("outage_minutes", None if ongoing else res - s, "minutes", integer=True, w=2,
                 instr="Total duration of the impact, from start to resolution")
    doc.duration("time_to_detect", det - s, "minutes", integer=True, w=1.5,
                 instr="Minutes from the start of the impact to the first alert")
    doc.items("affected_services", svcs, "text", w=1.5)
    doc.number("customers_affected", customers, integer=True, instr="Number of customers reported as affected")
    printed_cause = known_cause and not ongoing
    doc.text("root_cause", cause if printed_cause else None, w=1.5)
    doc.text("on_call_engineer", oncall, instr="Engineer who was paged")
    if layout == "report":
        doc.items("follow_up_due_dates", [d for _, _, d in fu], "date", instr="Due dates of the follow-up actions")
        doc.datetime("review_meeting", review[0] if review else None, review[1] if review else None,
                     instr="Date and time of the post-incident review")
    doc.text("status_page_url", None, w=0.7, instr="Link to the public status page entry")
    doc.text("change_request_id", None, instr="ID of the change request linked to the incident")
    doc.money("service_credit", None, instr="Service credit offered to affected customers")
    return doc
