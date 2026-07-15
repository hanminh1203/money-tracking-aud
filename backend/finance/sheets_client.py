"""Google Sheets API client — port of frontend/src/lib/sheetsApi.js."""

from __future__ import annotations

import re
import uuid
from typing import Any

import requests
from django.conf import settings

from finance import db_writer

BASE = 'https://sheets.googleapis.com/v4/spreadsheets'

INPUT_COLUMNS = ['Date', 'Change', 'Source', 'Comment', 'Sub category']
RECEIPT_COLUMNS = ['Receipt ID', 'Date', 'Total']
RECEIPT_ITEM_COLUMNS = ['Receipt ID', 'Name', 'Amount', 'Unit', 'Money']
RECEIPT_TX_COLUMNS = [
    'Date',
    'Change',
    'Source',
    'Comment',
    'Sub category',
    'Receipt ID',
]


class SheetsError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def parse_amount(val: Any) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    if not val:
        return 0.0
    cleaned = re.sub(r'[^0-9.\-]', '', str(val))
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def column_letter(index: int) -> str:
    n = index + 1
    s = ''
    while n > 0:
        rem = (n - 1) % 26
        s = chr(65 + rem) + s
        n = (n - 1) // 26
    return s


def quote_sheet_title(title: str) -> str:
    if re.match(r'^[A-Za-z0-9_]+$', title):
        return title
    return "'" + title.replace("'", "''") + "'"


class SheetsClient:
    def __init__(self, access_token: str):
        self.token = access_token
        self.sheet_id = settings.SHEET_ID
        if not self.sheet_id:
            raise SheetsError('SHEET_ID is not configured')
        self._tables_cache: dict[str, dict] | None = None

    def request(self, path: str, method: str = 'GET', json_body: Any = None) -> Any:
        url = f'{BASE}/{self.sheet_id}{path}'
        res = requests.request(
            method,
            url,
            headers={
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/json',
            },
            json=json_body,
            timeout=60,
        )
        if not res.ok:
            try:
                body = res.json()
                msg = body.get('error', {}).get('message') or f'{res.status_code} {res.reason}'
            except Exception:
                msg = f'{res.status_code} {res.reason}'
            raise SheetsError(msg, status=res.status_code)
        if res.status_code == 204 or not res.content:
            return {}
        return res.json()

    def get_tables(self) -> dict[str, dict]:
        if self._tables_cache is not None:
            return self._tables_cache
        data = self.request(
            '?fields=sheets(properties(sheetId,title),tables(name,range,columnProperties))'
        )
        by_name: dict[str, dict] = {}
        for sheet in data.get('sheets') or []:
            props = sheet.get('properties') or {}
            for table in sheet.get('tables') or []:
                cols = table.get('columnProperties') or []
                columns = sorted(
                    [
                        {
                            'index': c.get('columnIndex', i),
                            'name': c.get('columnName'),
                        }
                        for i, c in enumerate(cols)
                    ],
                    key=lambda c: c['index'],
                )
                by_name[table['name']] = {
                    'sheetId': props.get('sheetId'),
                    'sheetTitle': props.get('title'),
                    'range': table.get('range'),
                    'columns': columns,
                }
        self._tables_cache = by_name
        return by_name

    def get_table(self, table_name: str) -> dict:
        tables = self.get_tables()
        t = tables.get(table_name)
        if not t:
            raise SheetsError(
                f'Table "{table_name}" not found. Did you run Convert to Table on it?'
            )
        return t

    @staticmethod
    def data_range_a1(t: dict) -> str:
        rng = t['range']
        start_col = column_letter(rng['startColumnIndex'])
        end_col = column_letter(rng['endColumnIndex'] - 1)
        start_row = rng['startRowIndex'] + 2
        end_row = rng['endRowIndex']
        return f"{quote_sheet_title(t['sheetTitle'])}!{start_col}{start_row}:{end_col}{end_row}"

    def get_values(self, a1_range: str) -> list[list]:
        data = self.request(f'/values/{requests.utils.quote(a1_range, safe="")}')
        return data.get('values') or []

    def batch_get_values(self, a1_ranges: list[str]) -> list[list[list]]:
        qs = '&'.join(f'ranges={requests.utils.quote(r, safe="")}' for r in a1_ranges)
        data = self.request(f'/values:batchGet?{qs}')
        return [vr.get('values') or [] for vr in data.get('valueRanges') or []]

    @staticmethod
    def find_col(headers: list, pattern: str) -> int:
        rx = re.compile(pattern, re.I)
        for i, h in enumerate(headers):
            if rx.search(str(h or '').strip()):
                return i
        return -1

    def get_transaction_data(self) -> dict:
        table = self.get_table(settings.COMPUTED_TRANSACTIONS_TABLE)
        values = self.get_values(self.data_range_a1(table))
        headers = [c['name'] for c in table['columns']]
        header_start_row = table['range']['startRowIndex'] + 2
        rows = []
        for i, row in enumerate(values):
            if not row or all(c == '' or c is None for c in row):
                continue
            obj = {h: (row[idx] if idx < len(row) else None) for idx, h in enumerate(headers)}
            obj['__row'] = header_start_row + i
            rows.append(obj)
        return {'headers': headers, 'rows': rows}

    def get_income_expense_by_month(self) -> list[dict]:
        table = self.get_table(settings.INCOME_EXPENSE_TABLE)
        values = self.get_values(self.data_range_a1(table))
        headers = [c['name'] for c in table['columns']]
        idx = {
            'month': self.find_col(headers, r'^month$'),
            'income': self.find_col(headers, r'^income$'),
            'expense': self.find_col(headers, r'^expense$'),
        }
        result = []
        for r in values:
            if idx['month'] < 0 or idx['month'] >= len(r) or not r[idx['month']]:
                continue
            result.append(
                {
                    'month': str(r[idx['month']]).strip(),
                    'income': parse_amount(r[idx['income']] if idx['income'] >= 0 else 0),
                    'expense': parse_amount(r[idx['expense']] if idx['expense'] >= 0 else 0),
                }
            )
        return result

    def get_metadata(self) -> dict:
        category_table = self.get_table(settings.CATEGORY_TABLE)
        sources_table = self.get_table(settings.SOURCES_TABLE)
        category_values, sources_values = self.batch_get_values(
            [self.data_range_a1(category_table), self.data_range_a1(sources_table)]
        )

        cat_headers = [c['name'] for c in category_table['columns']]
        cat_idx = {
            'main': self.find_col(cat_headers, r'^main category$'),
            'sub': self.find_col(cat_headers, r'^sub ?category$'),
            'type': self.find_col(cat_headers, r'^type$'),
        }
        categories = []
        for r in category_values:
            if cat_idx['main'] < 0 or cat_idx['sub'] < 0:
                continue
            if cat_idx['main'] >= len(r) or cat_idx['sub'] >= len(r):
                continue
            if not r[cat_idx['main']] or not r[cat_idx['sub']]:
                continue
            categories.append(
                {
                    'mainCategory': str(r[cat_idx['main']]).strip(),
                    'subCategory': str(r[cat_idx['sub']]).strip(),
                    'type': (
                        str(r[cat_idx['type']] or '').strip()
                        if cat_idx['type'] >= 0 and cat_idx['type'] < len(r)
                        else ''
                    ),
                }
            )

        src_headers = [c['name'] for c in sources_table['columns']]
        src_idx = {
            'name': self.find_col(src_headers, r'^name$'),
            'type': self.find_col(src_headers, r'^type$'),
        }
        sources = []
        for r in sources_values:
            if src_idx['name'] < 0 or src_idx['name'] >= len(r) or not r[src_idx['name']]:
                continue
            sources.append(
                {
                    'name': str(r[src_idx['name']]).strip(),
                    'type': (
                        str(r[src_idx['type']] or '').strip()
                        if src_idx['type'] >= 0 and src_idx['type'] < len(r)
                        else ''
                    ),
                }
            )

        return {'sources': sources, 'categories': categories}

    def append_rows(self, table_name: str, column_names: list[str], rows: list[list]) -> None:
        if not rows:
            return
        table = self.get_table(table_name)
        col_index: dict[str, int] = {}
        for name in column_names:
            col = next((c for c in table['columns'] if c['name'] == name), None)
            if not col:
                raise SheetsError(f'Column "{name}" not found in table "{table_name}"')
            col_index[name] = col['index']

        indices = [col_index[n] for n in column_names]
        min_col = min(indices)
        max_col = max(indices)
        if max_col - min_col != len(column_names) - 1:
            raise SheetsError(f'Columns must be contiguous in table "{table_name}"')

        ordered_rows = []
        for values in rows:
            paired = [
                {'index': col_index[name], 'value': values[i]}
                for i, name in enumerate(column_names)
            ]
            paired.sort(key=lambda x: x['index'])
            ordered_rows.append([x['value'] for x in paired])

        start_col = column_letter(min_col)
        end_col = column_letter(max_col)
        start_row = table['range']['startRowIndex'] + 2
        append_range = (
            f"{quote_sheet_title(table['sheetTitle'])}!{start_col}{start_row}:{end_col}"
        )
        self.request(
            f'/values/{requests.utils.quote(append_range, safe="")}'
            f':append?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS',
            method='POST',
            json_body={'values': ordered_rows},
        )

    def append_transaction_row(self, values: list) -> None:
        self.append_rows(settings.TRANSACTIONS_TABLE, INPUT_COLUMNS, [values])

    def add_transaction(
        self,
        *,
        date: str,
        amount: Any,
        type: str,
        source: str,
        sub_category: str = '',
        comment: str = '',
    ) -> dict:
        try:
            abs_amt = abs(float(amount))
        except (TypeError, ValueError):
            raise SheetsError('Invalid amount')
        if not abs_amt:
            raise SheetsError('Invalid amount')
        if not source:
            raise SheetsError('Source is required')
        signed = -abs_amt if type == 'Expense' else abs_amt
        self.append_transaction_row([date, signed, source, comment or '', sub_category or ''])
        db_writer.save_transaction(
            date=date,
            change=signed,
            source=source,
            comment=comment or '',
            sub_category=sub_category or '',
        )
        return {'added': 1}

    def add_transfer(
        self,
        *,
        date: str,
        amount: Any,
        from_source: str,
        to_source: str,
        comment: str = '',
    ) -> dict:
        try:
            abs_amt = abs(float(amount))
        except (TypeError, ValueError):
            raise SheetsError('Invalid amount')
        if not abs_amt:
            raise SheetsError('Invalid amount')
        if not from_source or not to_source:
            raise SheetsError('Both sources are required')
        if from_source == to_source:
            raise SheetsError('Source and destination must differ')
        note = comment or 'Exchange'
        self.append_transaction_row([date, -abs_amt, from_source, note, 'Exchange (self)'])
        self.append_transaction_row([date, abs_amt, to_source, note, 'Exchange (self)'])
        db_writer.save_transactions(
            [
                {
                    'date': date,
                    'change': -abs_amt,
                    'source': from_source,
                    'comment': note,
                    'sub_category': 'Exchange (self)',
                },
                {
                    'date': date,
                    'change': abs_amt,
                    'source': to_source,
                    'comment': note,
                    'sub_category': 'Exchange (self)',
                },
            ]
        )
        return {'added': 2}

    def add_receipt(
        self,
        *,
        date: str,
        store: str,
        sub_category: str,
        comment: str = '',
        sources: list[dict],
        items: list[dict],
    ) -> dict:
        if not date:
            raise SheetsError('Date is required')
        if not (store or '').strip():
            raise SheetsError('Store is required')
        if not sub_category:
            raise SheetsError('Sub category is required')
        if not items:
            raise SheetsError('At least one item is required')
        if not sources:
            raise SheetsError('At least one payment source is required')

        normalized_items = []
        for i, it in enumerate(items):
            name = str(it.get('name') or '').strip()
            try:
                amount = float(it.get('amount'))
            except (TypeError, ValueError):
                raise SheetsError(f'Item {i + 1}: invalid amount')
            unit = str(it.get('unit') or '').strip()
            try:
                money = abs(float(it.get('money')))
            except (TypeError, ValueError):
                raise SheetsError(f'Item {i + 1}: invalid money')
            if not name:
                raise SheetsError(f'Item {i + 1}: name is required')
            if not unit:
                raise SheetsError(f'Item {i + 1}: unit is required')
            if not money:
                raise SheetsError(f'Item {i + 1}: invalid money')
            normalized_items.append(
                {'name': name, 'amount': amount, 'unit': unit, 'money': money}
            )

        normalized_sources = []
        for i, s in enumerate(sources):
            source = str(s.get('source') or '').strip()
            try:
                amount = abs(float(s.get('amount')))
            except (TypeError, ValueError):
                raise SheetsError(f'Source {i + 1}: invalid amount')
            if not source:
                raise SheetsError(f'Source {i + 1}: source is required')
            if not amount:
                raise SheetsError(f'Source {i + 1}: invalid amount')
            normalized_sources.append({'source': source, 'amount': amount})

        total = round(sum(it['money'] for it in normalized_items) * 100) / 100
        source_total = round(sum(s['amount'] for s in normalized_sources) * 100) / 100
        if abs(total - source_total) > 0.009:
            raise SheetsError(
                f'Source amounts ({source_total}) must equal items total ({total})'
            )

        receipt_id = str(uuid.uuid4())
        comment_text = f'{(store or "").strip()} : {comment or ""}'.strip()

        self.append_rows(
            settings.RECEIPT_TABLE, RECEIPT_COLUMNS, [[receipt_id, date, total]]
        )
        self.append_rows(
            settings.RECEIPT_ITEMS_TABLE,
            RECEIPT_ITEM_COLUMNS,
            [
                [receipt_id, it['name'], it['amount'], it['unit'], it['money']]
                for it in normalized_items
            ],
        )
        self.append_rows(
            settings.TRANSACTIONS_TABLE,
            RECEIPT_TX_COLUMNS,
            [
                [date, -s['amount'], s['source'], comment_text, sub_category, receipt_id]
                for s in normalized_sources
            ],
        )

        db_writer.save_receipt_bundle(
            receipt_id=receipt_id,
            date=date,
            total=total,
            items=normalized_items,
            transactions=[
                {
                    'date': date,
                    'change': -s['amount'],
                    'source': s['source'],
                    'comment': comment_text,
                    'sub_category': sub_category,
                }
                for s in normalized_sources
            ],
        )

        return {
            'receiptId': receipt_id,
            'total': total,
            'items': len(normalized_items),
            'transactions': len(normalized_sources),
        }
