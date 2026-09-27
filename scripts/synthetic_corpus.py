from __future__ import annotations

from datetime import date

from app import config
from app.models import Document, Section, approx_token_count, make_chunk_id, utcnow

PROSE = {
    "overview": (
        "{name} is an open ended {category} scheme sponsored by {amc}. The scheme seeks to "
        "generate long term capital appreciation from a diversified portfolio of equity "
        "securities, subject to the investment objective and the restrictions stated in the "
        "scheme information document. The fund is benchmarked against {benchmark} and is "
        "managed by {manager}. The scheme was launched on {inception} and is administered by "
        "{rta}. Investors should read the scheme information document, key information "
        "memorandum and statement of additional information before investing, because this "
        "summary cannot replace those documents. Past performance is not indicative of future "
        "results, and mutual fund investments are subject to market risks. The asset "
        "allocation may be changed by the fund manager within the limits permitted by the "
        "scheme regulations, and the risk profile of the scheme may therefore change over "
        "time. Please read all scheme related documents carefully before making an investment "
        "decision."
    ),
    "objective": (
        "The primary investment objective of {name} is to invest in a diversified portfolio "
        "of {category} securities with the aim of providing long term capital appreciation. "
        "The scheme intends to maintain a portfolio which is broadly representative of the "
        "{benchmark} index while allowing the manager discretion over individual securities. "
        "The scheme follows a long term investment horizon and is not designed for short term "
        "capital gains. Securities may be acquired, redeemed or switched as per the "
        "restrictions described in the scheme information document, and the portfolio may be "
        "rebalanced from time to time in response to changes in market conditions, fund flows "
        "and applicable regulations."
    ),
    "structure": (
        "The scheme is an open ended mutual fund and units are allotted at the applicable net "
        "asset value on the day of allotment. The net asset value is calculated after deducting "
        "the accrued expenses, including the management fee and statutory levies, from the "
        "value of the underlying portfolio. Units are listed on the recognised stock exchange "
        "for the purpose of trading and are also transferable. The registrar and transfer "
        "agent maintains the unit holder register and processes redemption and switch "
        "requests. Suspension of redemption, if any, is governed by the regulations and would "
        "be notified to investors through the fund's official communication channels."
    ),
    "risk": (
        "The riskometer of the scheme is {risk} as published by the asset management company in "
        "line with the applicable regulations. The riskometer is a month-end assessment and is "
        "revised monthly; the investor should refer to the latest monthly portfolio "
        "disclosure for the current riskometer category rather than relying on a historical "
        "value. The scheme carries equity risk because a significant portion of the portfolio "
        "is invested in equities, whose prices are subject to market volatility. Concentration "
        "risk may arise where holdings are concentrated in a small number of securities, "
        "liquidity risk may arise where a security cannot be sold at the quoted price, and "
        "tracking risk may arise where the portfolio deviates from the benchmark."
    ),
}

HOLDING_ROWS = [
    ("Reliance Industries", "9.12"),
    ("HDFC Bank", "8.44"),
    ("ICICI Bank", "7.91"),
    ("Infosys", "6.05"),
    ("State Bank of India", "5.38"),
    ("Tata Consultancy Services", "4.92"),
    ("Bharti Airtel", "4.31"),
    ("ITC", "3.88"),
    ("Hindustan Unilever", "3.55"),
    ("Larsen & Toubro", "3.21"),
    ("Axis Bank", "2.94"),
    ("Kotak Mahindra Bank", "2.61"),
    ("Sun Pharmaceutical", "2.18"),
    ("Maruti Suzuki", "2.05"),
    ("HCL Technologies", "1.88"),
    ("Tata Motors", "1.72"),
    ("Adani Ports", "1.54"),
    ("Bajaj Finance", "1.31"),
    ("Nestle India", "1.19"),
    ("Power Grid Corporation", "1.02"),
]

DETAIL = {
    "S1": {
        "category": "large cap",
        "benchmark": "NIFTY 100 TRI",
        "risk": "Moderately High",
        "expense_ratio": "1.03",
        "exit_load": "Exit load of 1% if redeemed within 1 year",
        "min_sip": "100",
        "min_amount": "100",
        "lock_in": None,
    },
    "S2": {
        "category": "flexi cap",
        "benchmark": "NIFTY 500 TRI",
        "risk": "Moderately High",
        "expense_ratio": "0.77",
        "exit_load": "Exit load of 1% if redeemed within 1 year",
        "min_sip": "100",
        "min_amount": "100",
        "lock_in": None,
    },
    "S3": {
        "category": "equity linked tax saving",
        "benchmark": "NIFTY 500 TRI",
        "risk": "Moderately High",
        "expense_ratio": "1.21",
        "exit_load": "Nil",
        "min_sip": "500",
        "min_amount": "500",
        "lock_in": "3 years",
    },
    "S4": {
        "category": "small cap",
        "benchmark": "NIFTY 250 TRI",
        "risk": "Moderately High",
        "expense_ratio": "0.78",
        "exit_load": "Exit load of 1% if redeemed within 1 year",
        "min_sip": "100",
        "min_amount": "100",
        "lock_in": None,
    },
    "S5": {
        "category": "balanced advantage",
        "benchmark": "NIFTY 50 Hybrid Composite Debt 50:50 Index",
        "risk": "Moderately High",
        "expense_ratio": "0.78",
        "exit_load": (
            "Exit Load for units in excess of 15% of the investment,1% will be charged for "
            "redemption within 1 year."
        ),
        "min_sip": "100",
        "min_amount": "100",
        "lock_in": None,
    },
}

META = {
    "S1": ("HDFC Large Cap Fund", "Prashant Jain", "01-Jan-2013"),
    "S2": ("HDFC Equity (Flexi Cap) Fund", "Prashant Jain", "01-Jan-2013"),
    "S3": ("HDFC ELSS Tax Saver Fund", "Siddharth Sinha", "01-Jan-2013"),
    "S4": ("HDFC Small Cap Fund", "Kireet Alva", "01-Jan-2013"),
    "S5": ("HDFC Balanced Advantage Fund", "Siddharth Sinha", "01-Jan-2013"),
}


def _section(title: str, body: str, level: int, page: int) -> tuple[str, str]:
    heading = f"{'#' * level} {title}"
    return heading, f"{heading}\n{body.strip()}"


def build_synthetic_documents() -> list[Document]:
    documents: list[Document] = []
    for scheme in config.SCHEMES:
        detail = DETAIL[scheme.scheme_id]
        name, manager, inception = META[scheme.scheme_id]
        values = {
            "name": name,
            "amc": "HDFC Mutual Fund",
            "category": detail["category"],
            "benchmark": detail["benchmark"],
            "manager": manager,
            "inception": inception,
            "rta": "RTA",
            "risk": detail["risk"],
        }
        holdings = "\n".join(
            f"{holding} | {weight}%" for holding, weight in HOLDING_ROWS
        )
        blocks: list[tuple[str, str, int]] = [
            (f"{name} (Direct Growth)", PROSE["overview"].format(**values), 1),
            ("Investment objective", PROSE["objective"].format(**values), 2),
            ("Scheme structure", PROSE["structure"].format(**values), 2),
            ("Portfolio and top holdings", f"Holding | Weight\n{holdings}", 2),
            ("Expense ratio", f"Expense ratio: {detail['expense_ratio']}%", 2),
            ("Exit load", f"Exit load: {detail['exit_load']}", 2),
            (
                "Minimum investment",
                f"Minimum SIP: Rs {detail['min_sip']}\nMinimum amount: Rs {detail['min_amount']}",
                2,
            ),
        ]
        if detail["lock_in"]:
            blocks.append(("Lock-in period", f"Lock-in period: {detail['lock_in']}", 2))
        blocks.append(
            ("Benchmark", f"Benchmark: {detail['benchmark']}", 2)
        )
        blocks.append(("Riskometer", f"Riskometer: {detail['risk']}", 2))
        blocks.append(("Risk management", PROSE["risk"].format(**values), 2))

        sections: list[Section] = []
        lines: list[str] = []
        offset = 0
        page = 1
        root_title = blocks[0][0]
        for ordinal, (title, body, level) in enumerate(blocks):
            heading, rendered = _section(title, body, level, page)
            lines.append(rendered)
            start = offset
            offset += len(rendered) + 1
            page += 1
            path = title if level == 1 else f"{root_title}>{title}"
            sections.append(
                Section(
                    title=title,
                    level=level,
                    text=rendered,
                    heading_path=path,
                    char_start=start,
                    char_end=start + len(rendered),
                    page=page - 1,
                    ordinal=ordinal,
                )
            )
        text = "\n".join(lines)
        fields = {
            "expense_ratio": detail["expense_ratio"],
            "exit_load": detail["exit_load"],
            "min_sip": detail["min_sip"],
            "min_amount": detail["min_amount"],
            "benchmark": detail["benchmark"],
            "riskometer": detail["risk"],
        }
        if detail["lock_in"]:
            fields["lock_in"] = detail["lock_in"]
        documents.append(
            Document(
                source_id=f"{scheme.scheme_id}_synthetic_factsheet",
                scheme_id=scheme.scheme_id,
                url=scheme.url,
                title=f"SYNTHETIC {name} factsheet-shaped document",
                source_type="factsheet",
                authority="official",
                extraction_method="pdf",
                retrieved_at=utcnow(),
                content_hash="synthetic",
                document_date=date(2026, 6, 30),
                fields=fields,
                is_complete=True,
                text=text,
                sections=sections,
            )
        )
    return documents


def synthetic_summary() -> str:
    documents = build_synthetic_documents()
    total = sum(approx_token_count(document.text) for document in documents)
    return (
        f"{len(documents)} synthetic documents, {total} tokens, "
        f"{sum(len(d.sections) for d in documents)} sections"
    )


if __name__ == "__main__":
    print(synthetic_summary())
    for document in build_synthetic_documents():
        print(
            f"  {document.source_id:28} tokens={approx_token_count(document.text):5} "
            f"sections={len(document.sections):3} fields={len(document.fields)}"
        )
    assert make_chunk_id("x", 1) == "x_c0001"
