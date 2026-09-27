from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag
from pypdf import PdfReader

from app import config
from app.ingest.fetch import FetchResult
from app.models import Document, ParsedDocument, Section, approx_token_count, as_utc, utcnow

DROP_TAGS = ("script", "style", "nav", "footer", "header", "noscript", "form")
DROP_PATTERN = re.compile(r"cookie|consent|popup|modal|newsletter|advert", re.I)
HEADING_TAGS = ("h1", "h2", "h3", "h4")
NEXT_DATA_PATTERN = re.compile(
    r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S
)
MIN_TEXT_TOKENS = 400
STRUCTURED_EXTRACTION_OVERRIDES_TOKEN_FLOOR = True

FIELD_KEYS = (
    "expense_ratio",
    "exit_load",
    "min_sip",
    "min_amount",
    "lock_in",
    "riskometer",
    "benchmark",
    "nav",
    "aum",
)

MIRROR_FIELD_MAP = {
    "expense_ratio": "expense_ratio",
    "exit_load": "exit_load",
    "min_sip_investment": "min_sip",
    "min_investment_amount": "min_amount",
    "nfo_risk": "riskometer",
    "benchmark": "benchmark",
    "nav": "nav",
    "aum": "aum",
}

PLAN_DIRECT = re.compile(r"\bdirect\b", re.I)
PLAN_REGULAR = re.compile(r"\bregular\b", re.I)

NUMBER = r"(\d+(?:[.,]\d+)*)"
PERCENT = r"(\d+(?:\.\d+)?)\s*%"

FIELD_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("expense_ratio", re.compile(r"(?:total\s+)?expense\s+ratio\s*(?:\(as\s+on[^)]*\))?\s*[:\-]?\s*" + PERCENT, re.I)),
    ("expense_ratio", re.compile(r"\bTER\b[^0-9]{0,40}" + PERCENT, re.I)),
    ("expense_ratio", re.compile(r"annual\s+management\s+charge[^0-9]{0,40}" + PERCENT, re.I)),
    ("exit_load", re.compile(r"exit\s+load[^.\n]{0,120}", re.I)),
    ("benchmark", re.compile(r"benchmark[^.\n]{0,120}", re.I)),
    ("riskometer", re.compile(r"riskometer[^.\n]{0,60}", re.I)),
    ("min_sip", re.compile(r"minimum\s+(?:sip|investment\s+via\s+sip)[^0-9]{0,40}" + NUMBER, re.I)),
    ("min_amount", re.compile(r"minimum\s+(?:investment|amount|investment\s+amount|purchase)[^0-9]{0,40}" + NUMBER, re.I)),
    ("lock_in", re.compile(r"lock[\s\-]?in\s+period[^0-9]{0,40}" + NUMBER, re.I)),
    ("nav", re.compile(r"\bNAV\b[^0-9]{0,30}" + NUMBER, re.I)),
    ("aum", re.compile(r"\bAUM\b[^0-9]{0,30}" + NUMBER, re.I)),
)

DIRECT_TER_PATTERN = re.compile(r"direct\s*(?:plan)?\s*[:\-]?\s*" + PERCENT, re.I)
REGULAR_TER_PATTERN = re.compile(r"regular\s*(?:plan)?\s*[:\-]?\s*" + PERCENT, re.I)
ISIN_PATTERN = re.compile(r"\b(IN[0-9A-Za-z]{10})\b", re.I)
DATE_PATTERN = re.compile(
    r"\b(?:as\s+(?:on|of)|as\s+at)\s*:?\s*("
    r"\d{1,2}[- ][A-Za-z]{3,9},?[- ]+\d{4}"
    r"|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}"
    r"|\d{4}-\d{2}-\d{2}"
    r"|[A-Za-z]{3,9}\s+\d{4}"
    r")",
    re.I,
)
MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "jan", "feb", "mar", "apr", "may", "jun",
            "jul", "aug", "sep", "oct", "nov", "dec",
        ],
        start=1,
    )
}


def normalise_riskometer(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\briskometer\b", "", value, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" :-")
    return cleaned or None


def format_lock_in(lock_in: Any) -> str | None:
    if not isinstance(lock_in, dict):
        return None
    parts: list[str] = []
    for unit, label in (("years", "year"), ("months", "month"), ("days", "day")):
        value = lock_in.get(unit)
        if isinstance(value, (int, float)) and value:
            parts.append(f"{int(value)} {label}{'s' if int(value) != 1 else ''}")
    return " ".join(parts) if parts else None


def format_amount(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return f"{value:,.0f}" if float(value).is_integer() else f"{value:,}"
    text = str(value).strip()
    return text or None


def coerce_date(raw: str) -> str | None:
    cleaned = re.sub(r"[,\s]+", " ", raw.replace("-", " ")).strip()
    tokens = cleaned.split()
    try:
        if re.fullmatch(r"\d{4} \d{1,2} \d{1,2}", cleaned):
            return date(int(tokens[0]), int(tokens[1]), int(tokens[2])).isoformat()
        if re.fullmatch(r"\d{1,2} [A-Za-z]{3,9} \d{4}", cleaned):
            return date(int(tokens[2]), MONTHS[tokens[1][:3].lower()], int(tokens[0])).isoformat()
        if re.fullmatch(r"[A-Za-z]{3,9} \d{1,2} \d{4}", cleaned):
            return date(int(tokens[2]), MONTHS[tokens[0][:3].lower()], int(tokens[1])).isoformat()
        if re.fullmatch(r"[A-Za-z]{3,9} \d{4}", cleaned):
            return date(int(tokens[1]), MONTHS[tokens[0][:3].lower()], 1).isoformat()
    except (KeyError, ValueError):
        return None
    return None


def normalise_date(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    direct = coerce_date(text)
    if direct:
        return direct
    match = DATE_PATTERN.search(text)
    if not match:
        return None
    return coerce_date(match.group(1))


def parse_document_date(value: str | None) -> str | None:
    return normalise_date(value)


def serialise_table(table: Any) -> str:
    rows: list[str] = []
    for row in table.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def strip_noise(soup: BeautifulSoup) -> None:
    for tag in soup.find_all(list(DROP_TAGS)):
        tag.decompose()
    for element in soup.find_all(True):
        ident = " ".join(
            filter(None, [element.get("class") and " ".join(element.get("class")), element.get("id")])
        )
        if ident and DROP_PATTERN.search(ident):
            element.decompose()


def _inside_heading(node: Any, root: Any) -> bool:
    parent = node.parent
    while parent is not None and parent is not root:
        if getattr(parent, "name", None) in HEADING_TAGS:
            return True
        parent = parent.parent
    return False


def parse_html_sections(html: str) -> tuple[str, list[Section]]:
    soup = BeautifulSoup(html, "lxml")
    strip_noise(soup)
    for table in soup.find_all("table"):
        table.replace_with(soup.new_string("\n" + serialise_table(table) + "\n"))

    body = soup.body or soup
    collected: list[dict[str, Any]] = []
    trail: list[tuple[int, str]] = []
    current: dict[str, Any] | None = None
    buffer: list[str] = []
    pending_space = False

    def flush() -> None:
        nonlocal buffer, pending_space
        if current is not None and buffer:
            joined = "\n".join(part for part in buffer if part).strip()
            if joined:
                current["lines"].append(joined)
        buffer = []
        pending_space = False

    def start(level: int, title: str) -> None:
        nonlocal current
        flush()
        while trail and trail[-1][0] >= level:
            trail.pop()
        trail.append((level, title))
        current = {
            "level": level,
            "title": title,
            "heading_path": ">".join(entry[1] for entry in trail),
            "lines": [f"{'#' * level} {title}"],
        }
        collected.append(current)

    for node in body.descendants:
        if isinstance(node, Tag):
            if node.name in HEADING_TAGS:
                title = node.get_text(" ", strip=True)
                if title:
                    start(int(node.name[1]), title)
            continue
        if not isinstance(node, NavigableString):
            continue
        if _inside_heading(node, body):
            continue
        raw = str(node)
        if not raw.strip():
            continue
        fragment = raw.strip()
        block = "\n" in fragment
        if buffer and pending_space and not block:
            buffer[-1] = f"{buffer[-1]} {fragment}"
        else:
            buffer.append(fragment)
        pending_space = not block
    flush()

    lines: list[str] = []
    sections: list[Section] = []
    offset = 0
    for ordinal, block in enumerate(collected):
        rendered = "\n".join(block["lines"]).strip()
        if not rendered:
            continue
        lines.append(rendered)
        start_offset = offset
        offset += len(rendered) + 1
        sections.append(
            Section(
                title=block["title"],
                level=block["level"],
                text=rendered,
                heading_path=block["heading_path"],
                char_start=start_offset,
                char_end=offset,
                ordinal=ordinal,
            )
        )
    return "\n".join(lines), sections


def fields_from_next_data(payload: dict[str, Any]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for source_key, target_key in MIRROR_FIELD_MAP.items():
        value = payload.get(source_key)
        if target_key == "riskometer":
            normalised = normalise_riskometer(value if isinstance(value, str) else None)
            if normalised:
                fields[target_key] = normalised
        elif source_key == "exit_load":
            if isinstance(value, str) and value.strip():
                fields[target_key] = value.strip()
        else:
            formatted = format_amount(value)
            if formatted:
                fields[target_key] = formatted
    lock_in = format_lock_in(payload.get("lock_in"))
    if lock_in:
        fields["lock_in"] = lock_in
    return fields


def mirror_sections(payload: dict[str, Any]) -> tuple[str, list[Section], dict[str, str]]:
    fields = fields_from_next_data(payload)
    fund_name = payload.get("fund_name") or payload.get("scheme_name") or "Fund"
    plan = " ".join(
        part for part in (payload.get("plan_type"), payload.get("scheme_type")) if part
    )
    groups: list[tuple[str, str]] = [
        (
            "Scheme identity",
            "\n".join(
                line
                for line in [
                    f"Fund: {fund_name}",
                    f"Plan: {plan}",
                    f"ISIN: {payload.get('isin')}",
                    f"Category: {payload.get('sub_category') or payload.get('category')}",
                    f"AMC: {payload.get('fund_house') or payload.get('amc')}",
                    f"Fund manager: {payload.get('fund_manager')}",
                    f"Inception date: {payload.get('launch_date')}",
                    f"Registrar: {payload.get('registrar_agent')}",
                ]
                if line.split(": ", 1)[1]
            ),
        ),
        (
            "Objective",
            str(payload.get("description") or "").strip(),
        ),
        (
            "Expense ratio",
            f"Expense ratio: {fields['expense_ratio']}%"
            if "expense_ratio" in fields
            else "",
        ),
        (
            "Exit load",
            f"Exit load: {fields['exit_load']}" if "exit_load" in fields else "",
        ),
        (
            "Minimum investment",
            "\n".join(
                line
                for line in [
                    f"Minimum SIP: Rs {fields['min_sip']}" if "min_sip" in fields else "",
                    f"Minimum amount: Rs {fields['min_amount']}" if "min_amount" in fields else "",
                ]
                if line
            ),
        ),
        (
            "Lock-in period",
            f"Lock-in period: {fields['lock_in']}" if "lock_in" in fields else "",
        ),
        (
            "Benchmark",
            "\n".join(
                line
                for line in [
                    f"Benchmark: {fields['benchmark']}" if "benchmark" in fields else "",
                    f"Benchmark name: {payload.get('benchmark_name')}"
                    if payload.get("benchmark_name")
                    else "",
                ]
                if line
            ),
        ),
        (
            "Riskometer",
            f"Riskometer: {fields['riskometer']}" if "riskometer" in fields else "",
        ),
        (
            "NAV and AUM",
            "\n".join(
                line
                for line in [
                    f"NAV: {fields['nav']}" if "nav" in fields else "",
                    f"NAV date: {payload.get('nav_date')}" if payload.get("nav_date") else "",
                    f"AUM: {fields['aum']} Cr" if "aum" in fields else "",
                ]
                if line
            ),
        ),
    ]
    holdings = payload.get("holdings")
    if isinstance(holdings, list) and holdings:
        rows = []
        for holding in holdings[:10]:
            if not isinstance(holding, dict):
                continue
            name = holding.get("name") or holding.get("company") or holding.get("holding_name")
            weight = holding.get("weight") or holding.get("percentage") or holding.get("weightage")
            if name:
                rows.append(f"{name} | {weight}" if weight is not None else str(name))
        if rows:
            groups.append(("Top holdings", "Holding | Weight\n" + "\n".join(rows)))

    lines: list[str] = []
    sections: list[Section] = []
    offset = 0
    for ordinal, (title, body) in enumerate(groups):
        if not body.strip():
            continue
        heading = f"## {title}"
        rendered = f"{heading}\n{body.strip()}"
        lines.append(rendered)
        start = offset
        offset += len(rendered) + 1
        sections.append(
            Section(
                title=title,
                level=2,
                text=rendered,
                heading_path=title,
                char_start=start,
                char_end=offset,
                ordinal=ordinal,
            )
        )
    return "\n".join(lines), sections, fields


def pdf_pages(content: bytes) -> list[str]:
    reader = PdfReader(__import__("io").BytesIO(content))
    return [(page.extract_text() or "") for page in reader.pages]


def scope_blocks(pages: list[str]) -> list[tuple[str | None, str]]:
    blocks: list[tuple[str | None, str]] = []
    carry = ""
    for text in pages:
        matches = list(ISIN_PATTERN.finditer(text))
        if not matches:
            carry += "\n" + text
            continue
        if carry.strip():
            blocks.append((None, carry))
            carry = ""
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            blocks.append((match.group(1).upper(), text[match.start() : end]))
    if carry.strip():
        blocks.append((None, carry))
    return blocks


def prefer_direct_ter(block: str) -> str | None:
    direct = DIRECT_TER_PATTERN.search(block)
    if direct:
        return f"{direct.group(1)}%"
    regular_only = REGULAR_TER_PATTERN.search(block)
    if regular_only and "direct" not in block.lower():
        return f"{regular_only.group(1)}%"
    generic = None
    for key, pattern in FIELD_PATTERNS:
        if key != "expense_ratio":
            continue
        match = pattern.search(block)
        if match:
            generic = f"{match.group(1)}%"
            break
    return generic


def select_scheme_blocks(
    blocks: list[tuple[str | None, str]], expected_isin: str | None
) -> list[tuple[str | None, str]]:
    if not expected_isin:
        return blocks
    wanted = expected_isin.strip().upper()
    return [block for block in blocks if block[0] and block[0].strip().upper() == wanted]


def extract_fields_from_blocks(
    blocks: list[tuple[str | None, str]], expected_isin: str | None = None
) -> dict[str, str]:
    scoped = select_scheme_blocks(blocks, expected_isin)
    if expected_isin and not scoped:
        return {}
    fields: dict[str, str] = {}
    for _, block in scoped:
        if not block.strip():
            continue
        ter = prefer_direct_ter(block)
        if ter and "expense_ratio" not in fields:
            fields["expense_ratio"] = ter
        for key, pattern in FIELD_PATTERNS:
            if key in fields or key == "expense_ratio":
                continue
            match = pattern.search(block)
            if not match:
                continue
            value = match.group(0).strip()
            if key in ("exit_load", "benchmark", "riskometer"):
                value = re.sub(r"\s+", " ", value)
            else:
                value = match.group(1).strip()
            fields[key] = value
    return fields


def build_pdf_document(
    content: bytes, expected_isin: str | None = None
) -> tuple[str, list[Section], dict[str, str], str | None]:
    pages = pdf_pages(content)
    blocks = scope_blocks(pages)
    fields = extract_fields_from_blocks(blocks, expected_isin)
    lines: list[str] = []
    sections: list[Section] = []
    offset = 0
    ordinal = 0
    for index, page in enumerate(pages, start=1):
        text = page.strip()
        if not text:
            continue
        title = f"Page {index}"
        rendered = f"## {title}\n{text}"
        lines.append(rendered)
        start = offset
        offset += len(rendered) + 1
        sections.append(
            Section(
                title=title,
                level=2,
                text=rendered,
                heading_path=title,
                char_start=start,
                char_end=offset,
                page=index,
                ordinal=ordinal,
            )
        )
        ordinal += 1
    document_date = None
    if pages:
        document_date = parse_document_date(pages[0][:2000])
    return "\n".join(lines), sections, fields, document_date


def missing_expected_facts(fields: dict[str, str], source: dict[str, Any]) -> list[str]:
    return [fact for fact in source.get("expected_facts", []) if fact not in fields]


def parse_document(fetch_result: FetchResult, source: dict[str, Any]) -> ParsedDocument:
    extraction_method = fetch_result.extraction_method
    if fetch_result.raw_path is None:
        return ParsedDocument(
            text="",
            sections=[],
            fields={},
            is_complete=False,
            extraction_method=extraction_method,
        )

    content = Path(fetch_result.raw_path).read_bytes()
    structured = False

    if fetch_result.is_pdf:
        text, sections, fields, document_date = build_pdf_document(
            content, source.get("isin")
        )
    else:
        html = content.decode("utf-8", errors="replace")
        payload = None
        if source.get("authority") == "mirror" or "groww.in" in source.get("url", ""):
            match = NEXT_DATA_PATTERN.search(html)
            if match:
                try:
                    decoded = json.loads(match.group(1))
                    payload = decoded["props"]["pageProps"]["mfServerSideData"]
                except (json.JSONDecodeError, KeyError, TypeError):
                    payload = None
        if payload:
            text, sections, fields = mirror_sections(payload)
            document_date = normalise_date(payload.get("nav_date"))
            structured = True
        else:
            text, sections = parse_html_sections(html)
            fields = extract_fields_from_blocks([(None, text)])
            document_date = parse_document_date(text[:2000])

    token_count = approx_token_count(text)
    missing = missing_expected_facts(fields, source)
    if structured and STRUCTURED_EXTRACTION_OVERRIDES_TOKEN_FLOOR:
        is_complete = not missing
    else:
        is_complete = not missing and token_count >= MIN_TEXT_TOKENS

    return ParsedDocument(
        text=text,
        sections=sections,
        fields=fields,
        is_complete=is_complete,
        extraction_method=extraction_method,
        document_date=document_date,
    )


def build_document(
    source: dict[str, Any],
    parsed: ParsedDocument,
    raw_meta: dict[str, Any] | None = None,
) -> Document:
    from app.models import Document, as_utc

    raw_meta = raw_meta or {}
    retrieved_raw = raw_meta.get("retrieved_at")
    retrieved_at = None
    if isinstance(retrieved_raw, str):
        try:
            retrieved_at = as_utc(datetime.fromisoformat(retrieved_raw))
        except ValueError:
            retrieved_at = None
    document_date = None
    if parsed.document_date:
        try:
            document_date = date.fromisoformat(parsed.document_date)
        except ValueError:
            document_date = None
    return Document(
        source_id=source["source_id"],
        scheme_id=source["scheme_id"],
        url=source["url"],
        title=source.get("title", source["source_id"]),
        source_type=source.get("source_type", ""),
        authority=source.get("authority", "official"),
        extraction_method=parsed.extraction_method,
        retrieved_at=retrieved_at or utcnow(),
        content_hash=raw_meta.get("content_hash") or "",
        document_date=document_date,
        fields=dict(parsed.fields),
        is_complete=parsed.is_complete,
        text=parsed.text,
        sections=list(parsed.sections),
    )


def load_raw_meta() -> dict[str, dict[str, Any]]:
    path = config.RAW_DIR / "index.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def load_corpus(include_incomplete: bool = False) -> list[Document]:
    raw_meta = load_raw_meta()
    documents: list[Document] = []
    for source in config.SOURCES:
        source_id = source["source_id"]
        md_path = config.PROCESSED_DIR / f"{source_id}.md"
        if not md_path.is_file():
            continue
        md_text = md_path.read_text(encoding="utf-8")
        separator = md_text.find("\n# ")
        body = md_text[separator + 1 :] if separator != -1 else md_text
        sections: list[Section] = []
        sections_path = config.PROCESSED_DIR / f"{source_id}.sections.json"
        if sections_path.is_file():
            try:
                sections = [
                    Section.from_dict(item)
                    for item in json.loads(sections_path.read_text(encoding="utf-8"))
                ]
            except (json.JSONDecodeError, KeyError, TypeError):
                sections = []
        fields: dict[str, str] = {}
        fields_path = config.PROCESSED_DIR / f"{source_id}.fields.json"
        document_date = None
        is_complete = True
        if fields_path.is_file():
            try:
                payload = json.loads(fields_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {}
            fields = payload.get("fields", {}) or {}
            document_date = payload.get("document_date")
            is_complete = bool(payload.get("is_complete"))
        if not include_incomplete and not is_complete:
            continue
        parsed = ParsedDocument(
            text=body,
            sections=sections,
            fields=fields,
            is_complete=is_complete,
            extraction_method=raw_meta.get(source_id, {}).get("extraction_method", ""),
            document_date=document_date,
        )
        documents.append(build_document(source, parsed, raw_meta.get(source_id, {})))
    return documents


def write_outputs(parsed: ParsedDocument, source: dict[str, Any]) -> dict[str, Path]:
    source_id = source["source_id"]
    config.ensure_dirs()
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    md_path = config.PROCESSED_DIR / f"{source_id}.md"
    sections_path = config.PROCESSED_DIR / f"{source_id}.sections.json"
    fields_path = config.PROCESSED_DIR / f"{source_id}.fields.json"

    header = [
        f"# {source.get('title', source_id)}",
        "",
        f"- source_id: {source_id}",
        f"- scheme_id: {source.get('scheme_id')}",
        f"- url: {source.get('url')}",
        f"- authority: {source.get('authority')}",
        f"- extraction_method: {parsed.extraction_method}",
        f"- document_date: {parsed.document_date}",
        f"- is_complete: {parsed.is_complete}",
        f"- tokens: {approx_token_count(parsed.text)}",
        "",
    ]
    md_path.write_text("\n".join(header) + parsed.text + "\n", encoding="utf-8")
    sections_path.write_text(
        json.dumps([section.to_dict() for section in parsed.sections], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    fields_payload = {
        "source_id": source_id,
        "scheme_id": source.get("scheme_id"),
        "authority": source.get("authority"),
        "is_complete": parsed.is_complete,
        "document_date": parsed.document_date,
        "missing_facts": missing_expected_facts(parsed.fields, source),
        "fields": parsed.fields,
    }
    fields_path.write_text(json.dumps(fields_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"md": md_path, "sections": sections_path, "fields": fields_path}
