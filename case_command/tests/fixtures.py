"""Synthetic litigation fixtures.

These are invented documents used to exercise the pipeline. They deliberately
mirror the *shape* of the real record — a PSC filing, a mortgage letter, shared
hardship evidence, a duplicate, a draft, a docketed order — without asserting
anything about the real cases.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

PSC_COMPLAINT = """\
BEFORE THE PUBLIC SERVICE COMMISSION OF WEST VIRGINIA

Case No. 26-0315-E-C

JACOB KERR,
    Complainant,
v.
APPALACHIAN POWER COMPANY,
    Respondent.

FORMAL COMPLAINT

1. Complainant is a residential customer of Appalachian Power Company (APCo).

2. On September 29, 2025, APCo terminated electric service to Complainant's
   residence.

3. The Public Service Commission entered a Final Order in Case No. 24-0735-E-C
   on September 3, 2025. The conduct complained of here occurred after that date
   and is not a relitigation of any issue decided in that proceeding.

4. Complainant did not receive pretermination written notice as required by
   150 C.S.R. 3.

5. APCo made no personal-contact attempt before terminating service.

6. Complainant requested a dispute meeting and did not receive a written decision.

7. On March 3, 2026, APCo conditioned restoration on payment of $3,130.73. The
   calculation of that amount has never been explained on the record.

WHEREFORE, Complainant respectfully requests that the Commission find that APCo
violated its tariff and the Commission's rules, order restoration of service, and
grant such other relief as is just.

Respectfully submitted this 5th day of March, 2026.
"""

APCO_ANSWER = """\
BEFORE THE PUBLIC SERVICE COMMISSION OF WEST VIRGINIA

Case No. 26-0315-E-C

APPALACHIAN POWER COMPANY'S ANSWER

Appalachian Power Company answers the Formal Complaint as follows:

1. Admitted that Complainant is a residential customer.

2. Admitted that service was terminated on September 29, 2025.

3. APCo asserts that the issues raised were decided in Case No. 24-0735-E-C by
   Final Order entered September 3, 2025, and are barred.

4. Denied. APCo states that written notice was mailed on September 12, 2025.

5. Denied. APCo states that personal contact was attempted on September 22, 2025.

6. APCo lacks sufficient information to admit or deny.

7. Admitted that $3,130.73 was quoted. The amount reflects arrears and a deposit.

APCo requests that the Complaint be dismissed.

Certificate of Service: A copy of the foregoing was served upon Complainant by
first-class mail on March 20, 2026.
"""

PSC_ORDER = """\
BEFORE THE PUBLIC SERVICE COMMISSION OF WEST VIRGINIA

Case No. 24-0735-E-C

FINAL ORDER

Entered: September 3, 2025

The Commission, having considered the record, hereby ORDERS that the complaint
is resolved on the terms stated herein. This matter is closed.

IT IS SO ORDERED.
"""

MORTGAGE_LETTER = """\
PHH Mortgage Services
Loss Mitigation Department

RE: Notice of Error — Qualified Written Request under RESPA
Loan Number: ending 4417

Dear Servicer:

This is a qualified written request under the Real Estate Settlement Procedures
Act, 12 U.S.C. 2605(e), and Regulation X, 12 C.F.R. 1024.35.

The escrow analysis dated January 14, 2026 does not reconcile with the payments
applied to the account. A loss mitigation application was submitted on
December 2, 2025 and has not been acknowledged within the time required.

The loan is a VA-guaranteed loan. Foreclosure referral would be improper while a
complete loss mitigation application is pending.

Please respond within the time required by 12 C.F.R. 1024.36.
"""

HARDSHIP_DECLARATION = """\
DECLARATION OF HARDSHIP

I, Jacob Kerr, declare as follows:

1. I am a veteran with a service-connected disability rated by the Department of
   Veterans Affairs.

2. Loss of electric service at my residence caused spoilage of food and loss of
   refrigerated medication.

3. Photographs and receipts documenting the loss are attached as exhibits.

4. The loss of service also affected my ability to maintain transportation and to
   attend medical appointments.

I declare under penalty of perjury that the foregoing is true and correct.
"""

DRAFT_MOTION = """\
DRAFT — DO NOT FILE

BEFORE THE PUBLIC SERVICE COMMISSION OF WEST VIRGINIA
Case No. 26-0315-E-C

MOTION FOR EXPEDITED RELIEF

[working copy — needs citation check]

Complainant moves for expedited relief regarding the termination of electric
service. This draft is a working copy and has not been filed.
"""

DOCKET_RECEIPT = """\
PUBLIC SERVICE COMMISSION OF WEST VIRGINIA
ELECTRONIC FILING RECEIPT

Case Number: 26-0315-E-C
Document: Formal Complaint
Filed: March 5, 2026
Confirmation Number: PSC-2026-0000418
Status: DOCKETED

This receipt confirms the document was received and docketed by the Commission.
"""

VA_LETTER = """\
DEPARTMENT OF VETERANS AFFAIRS
Regional Office

RE: Special Monthly Compensation — dependent status

This letter concerns your VA disability compensation and your request regarding
special monthly compensation. Your service-connected evaluation remains in effect.

You may appeal this decision to the Board of Veterans' Appeals within one year.
"""


def build_fixture_tree(root: Path) -> dict[str, Path]:
    """Create a fixture litigation tree under *root*. Returns named paths."""
    from ..config import (
        ARCHIVE, BRIDGEPORT, FINAL_FILINGS, INBOX, MORTGAGE, OTHER_CASES,
        PSC_AEP, SHARED_EVIDENCE, VETERANS,
    )

    for folder in (INBOX, PSC_AEP, MORTGAGE, BRIDGEPORT, VETERANS, OTHER_CASES,
                   SHARED_EVIDENCE, FINAL_FILINGS, ARCHIVE):
        (root / folder).mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}

    def write(name: str, folder: str, filename: str, content: str) -> None:
        path = root / folder / filename
        path.write_text(content, encoding="utf-8")
        paths[name] = path

    write("psc_complaint", INBOX, "PSC_26-0315_Formal_Complaint.txt", PSC_COMPLAINT)
    write("apco_answer", INBOX, "APCo_Answer_26-0315.txt", APCO_ANSWER)
    write("psc_order", INBOX, "PSC_Final_Order_24-0735.txt", PSC_ORDER)
    write("mortgage", INBOX, "PHH_RESPA_Qualified_Written_Request.txt", MORTGAGE_LETTER)
    write("hardship", INBOX, "Hardship_Declaration.txt", HARDSHIP_DECLARATION)
    write("draft", INBOX, "DRAFT_Motion_Expedited_Relief.txt", DRAFT_MOTION)
    write("receipt", INBOX, "PSC_Filing_Receipt_Confirmation.txt", DOCKET_RECEIPT)
    write("va", INBOX, "VA_SMC_Decision_Letter.txt", VA_LETTER)

    # A byte-identical duplicate in a different folder, of the kind another tool
    # leaves behind when it "organizes" a Drive folder.
    duplicate = root / ARCHIVE / "copy_of_complaint.txt"
    duplicate.write_text(PSC_COMPLAINT, encoding="utf-8")
    paths["duplicate"] = duplicate

    # A litigation packet.
    packet = root / INBOX / "litigation_packet.zip"
    with zipfile.ZipFile(packet, "w") as archive:
        archive.writestr("exhibit_a_notes.txt",
                         "Exhibit A: photographs of spoiled food dated October 1, 2025.")
        archive.writestr("exhibit_b_receipt.txt",
                         "Exhibit B: receipt for generator rental, $184.22, October 2, 2025.")
    paths["packet"] = packet

    return paths
