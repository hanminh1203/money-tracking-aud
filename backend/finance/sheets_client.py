"""Google Sheets API client — port of frontend/src/lib/sheetsApi.js."""

from __future__ import annotations

import re
import uuid
from datetime import date as date_cls
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
GIFTCARD_COLUMNS = ['Giftcard ID', 'Shop', 'Date', 'Balance']
# Giftcard ID sits after Receipt ID so columns stay contiguous in the sheet table.
GIFTCARD_TX_COLUMNS = [
    'Date',
    'Change',
    'Source',
    'Comment',
    'Sub category',
    'Receipt ID',
    'Giftcard ID',
]
GIFTCARD_SOURCE_NAME = 'Giftcard'

# Export column formats for Australian locale workbooks.
EXPORT_AUD_CURRENCY = {'type': 'CURRENCY', 'pattern': '"$"#,##0.00'}
EXPORT_AU_DATE = {'type': 'DATE', 'pattern': 'd/mm/yyyy'}
# Logical export table key → column name → numberFormat.
EXPORT_COLUMN_FORMATS: dict[str, dict[str, dict[str, str]]] = {
    'transactions': {
        'Date': EXPORT_AU_DATE,
        'Change': EXPORT_AUD_CURRENCY,
    },
    'giftcards': {
        'Date': EXPORT_AU_DATE,
        'Balance': EXPORT_AUD_CURRENCY,
    },
    'receipt': {
        'Date': EXPORT_AU_DATE,
        'Total': EXPORT_AUD_CURRENCY,
    },
    'receipt_items': {
        'Money': EXPORT_AUD_CURRENCY,
    },
}


def _export_column_property(table_key: str, column_index: int, column_name: str) -> dict[str, Any]:
    """Build addTable columnProperties entry; set DATE/CURRENCY types when mapped."""
    prop: dict[str, Any] = {
        'columnIndex': column_index,
        'columnName': column_name,
    }
    fmt = (EXPORT_COLUMN_FORMATS.get(table_key) or {}).get(column_name)
    if fmt and fmt.get('type') in ('CURRENCY', 'DATE'):
        prop['columnType'] = fmt['type']
    return prop


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
    def __init__(self, access_token: str, sheet_id: str, user=None):
        self.token = access_token
        self.sheet_id = (sheet_id or '').strip()
        if not self.sheet_id:
            raise SheetsError('Sheet ID is not configured for this user')
        self.user = user
        self._tables_cache: dict[str, dict] | None = None

    def _headers(self) -> dict[str, str]:
        return {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json',
        }

    def _raise_for_response(self, res: requests.Response) -> Any:
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

    def request(
        self,
        path: str,
        method: str = 'GET',
        json_body: Any = None,
        *,
        spreadsheet_id: str | None = None,
    ) -> Any:
        sid = spreadsheet_id if spreadsheet_id is not None else self.sheet_id
        url = f'{BASE}/{sid}{path}'
        res = requests.request(
            method,
            url,
            headers=self._headers(),
            json=json_body,
            timeout=60,
        )
        return self._raise_for_response(res)

    def create_spreadsheet(self, title: str, sheet_titles: list[str]) -> dict:
        """Create a new spreadsheet with one tab per title; returns API response."""
        if not sheet_titles:
            raise SheetsError('At least one sheet title is required')
        body = {
            'properties': {'title': title, 'locale': 'en_AU'},
            'sheets': [
                {'properties': {'sheetId': i, 'title': name}}
                for i, name in enumerate(sheet_titles)
            ],
        }
        res = requests.post(BASE, headers=self._headers(), json=body, timeout=60)
        return self._raise_for_response(res)

    def export_workbook(self, title: str, tables: dict[str, dict]) -> dict:
        """Create a new spreadsheet with named tables and Postgres export rows.

        ``tables`` maps logical keys to
        ``{table_name, columns, rows}`` (rows without header).
        Returns ``{spreadsheetId, url, counts}``.
        """
        if not tables:
            raise SheetsError('No tables to export')

        # Stable order matching Management UI.
        order = (
            'transactions',
            'giftcards',
            'receipt',
            'receipt_items',
            'category',
            'sources',
        )
        entries = []
        for key in order:
            if key not in tables:
                continue
            entry = tables[key]
            entries.append(
                {
                    'key': key,
                    'table_name': entry['table_name'],
                    'columns': list(entry['columns']),
                    'rows': list(entry['rows']),
                }
            )
        for key, entry in tables.items():
            if key in {e['key'] for e in entries}:
                continue
            entries.append(
                {
                    'key': key,
                    'table_name': entry['table_name'],
                    'columns': list(entry['columns']),
                    'rows': list(entry['rows']),
                }
            )

        sheet_titles = [e['table_name'] for e in entries]
        created = self.create_spreadsheet(title, sheet_titles)
        spreadsheet_id = created.get('spreadsheetId')
        if not spreadsheet_id:
            raise SheetsError('Spreadsheet create did not return an id')

        value_data = []
        add_table_requests = []
        format_requests = []
        counts: dict[str, int] = {}

        for i, entry in enumerate(entries):
            columns = entry['columns']
            rows = entry['rows']
            counts[entry['key']] = len(rows)
            n_cols = len(columns)
            # Header row + data rows (exclusive end). Empty tables still get a header.
            end_row = 1 + len(rows)
            add_table_requests.append(
                {
                    'addTable': {
                        'table': {
                            'name': entry['table_name'],
                            'range': {
                                'sheetId': i,
                                'startRowIndex': 0,
                                'endRowIndex': end_row,
                                'startColumnIndex': 0,
                                'endColumnIndex': n_cols,
                            },
                            'columnProperties': [
                                _export_column_property(entry['key'], col_i, name)
                                for col_i, name in enumerate(columns)
                            ],
                        }
                    }
                }
            )
            if rows:
                # Data starts under the table header (row 2 in A1 notation).
                range_a1 = f"{quote_sheet_title(entry['table_name'])}!A2"
                value_data.append({'range': range_a1, 'values': rows})
                col_formats = EXPORT_COLUMN_FORMATS.get(entry['key']) or {}
                for col_name, number_format in col_formats.items():
                    try:
                        col_index = columns.index(col_name)
                    except ValueError:
                        continue
                    format_requests.append(
                        {
                            'repeatCell': {
                                'range': {
                                    'sheetId': i,
                                    'startRowIndex': 1,
                                    'endRowIndex': end_row,
                                    'startColumnIndex': col_index,
                                    'endColumnIndex': col_index + 1,
                                },
                                'cell': {
                                    'userEnteredFormat': {
                                        'numberFormat': number_format,
                                    }
                                },
                                'fields': 'userEnteredFormat.numberFormat',
                            }
                        }
                    )

        # Create named tables (headers from columnProperties) before writing data.
        self.request(
            ':batchUpdate',
            method='POST',
            spreadsheet_id=spreadsheet_id,
            json_body={'requests': add_table_requests},
        )
        if value_data:
            self.request(
                '/values:batchUpdate',
                method='POST',
                spreadsheet_id=spreadsheet_id,
                json_body={
                    'valueInputOption': 'USER_ENTERED',
                    'data': value_data,
                },
            )
        if format_requests:
            self.request(
                ':batchUpdate',
                method='POST',
                spreadsheet_id=spreadsheet_id,
                json_body={'requests': format_requests},
            )

        return {
            'spreadsheetId': spreadsheet_id,
            'url': f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit',
            'counts': counts,
        }

    def check_connection(self) -> dict:
        """Lightweight probe — spreadsheet metadata only."""
        data = self.request('?fields=properties.title,spreadsheetId')
        props = data.get('properties') or {}
        return {
            'spreadsheet_id': data.get('spreadsheetId'),
            'title': props.get('title'),
        }

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

    @staticmethod
    def _parse_a1_start_row(a1_range: str) -> int:
        """Extract the starting 1-based row from an A1 range like 'Sheet!A12:E14'."""
        m = re.search(r'![A-Za-z]+(\d+)', a1_range or '')
        if not m:
            raise SheetsError(f'Could not parse sheet row from range: {a1_range!r}')
        return int(m.group(1))

    @staticmethod
    def _rows_as_dicts(table: dict, values: list[list]) -> list[dict]:
        headers = [c['name'] for c in table['columns']]
        start_row = table['range']['startRowIndex'] + 2
        rows: list[dict] = []
        for i, row in enumerate(values):
            if not row or all(c == '' or c is None for c in row):
                continue
            d = {h: (row[idx] if idx < len(row) else None) for idx, h in enumerate(headers)}
            d['__sheet_row'] = start_row + i
            rows.append(d)
        return rows

    def get_mirror_source_rows(self) -> dict[str, list[dict]]:
        """Read user-owned mirror tables (Transactions, Receipt, Receipt_Items, Giftcard)."""
        tx_table = self.get_table(settings.TRANSACTIONS_TABLE)
        receipt_table = self.get_table(settings.RECEIPT_TABLE)
        items_table = self.get_table(settings.RECEIPT_ITEMS_TABLE)
        giftcard_table = self.get_table(settings.GIFTCARD_TABLE)
        (
            tx_vals,
            receipt_vals,
            item_vals,
            giftcard_vals,
        ) = self.batch_get_values(
            [
                self.data_range_a1(tx_table),
                self.data_range_a1(receipt_table),
                self.data_range_a1(items_table),
                self.data_range_a1(giftcard_table),
            ]
        )
        return {
            'transactions': self._rows_as_dicts(tx_table, tx_vals),
            'receipts': self._rows_as_dicts(receipt_table, receipt_vals),
            'receipt_items': self._rows_as_dicts(items_table, item_vals),
            'giftcards': self._rows_as_dicts(giftcard_table, giftcard_vals),
        }

    def update_table_cell_at_row(
        self,
        table_name: str,
        *,
        sheet_row: int,
        update_column: str,
        new_value: Any,
    ) -> None:
        """Update a single cell in a sheet table at a known 1-based sheet row."""
        table = self.get_table(table_name)
        update_col = next((c for c in table['columns'] if c['name'] == update_column), None)
        if not update_col:
            raise SheetsError(f'Column "{update_column}" not found in table "{table_name}"')
        col_letter = column_letter(update_col['index'])
        a1 = f"{quote_sheet_title(table['sheetTitle'])}!{col_letter}{int(sheet_row)}"
        self.request(
            f'/values/{requests.utils.quote(a1, safe="")}?valueInputOption=USER_ENTERED',
            method='PUT',
            json_body={'values': [[new_value]]},
        )

    def update_table_cell(
        self,
        table_name: str,
        *,
        match_column: str,
        match_value: str,
        update_column: str,
        new_value: Any,
    ) -> None:
        """Update a single cell in a sheet table row matched by column value."""
        table = self.get_table(table_name)
        headers = [c['name'] for c in table['columns']]
        match_idx = self.find_col(headers, rf'^{re.escape(match_column)}$')
        if match_idx < 0:
            raise SheetsError(f'Column "{match_column}" not found in table "{table_name}"')

        values = self.get_values(self.data_range_a1(table))
        start_row = table['range']['startRowIndex'] + 2
        sheet_row = None
        for i, row in enumerate(values):
            cell = row[match_idx] if match_idx < len(row) else None
            if str(cell or '').strip() == str(match_value).strip():
                sheet_row = start_row + i
                break
        if sheet_row is None:
            raise SheetsError(
                f'No row with {match_column}={match_value!r} in table "{table_name}"'
            )
        self.update_table_cell_at_row(
            table_name,
            sheet_row=sheet_row,
            update_column=update_column,
            new_value=new_value,
        )

    def append_rows(self, table_name: str, column_names: list[str], rows: list[list]) -> list[int]:
        """Append rows; return 1-based sheet row numbers for each appended row."""
        if not rows:
            return []
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
        resp = self.request(
            f'/values/{requests.utils.quote(append_range, safe="")}'
            f':append?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS',
            method='POST',
            json_body={'values': ordered_rows},
        )
        # Table metadata (end row) may have grown.
        self._tables_cache = None
        updated = (resp.get('updates') or {}).get('updatedRange') or ''
        first_row = self._parse_a1_start_row(updated)
        return list(range(first_row, first_row + len(ordered_rows)))

    def append_transaction_row(self, values: list) -> int:
        row_numbers = self.append_rows(settings.TRANSACTIONS_TABLE, INPUT_COLUMNS, [values])
        return row_numbers[0]

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
        row_number = self.append_transaction_row(
            [date, signed, source, comment or '', sub_category or '']
        )
        db_writer.save_transaction(
            user=self.user,
            date=date,
            change=signed,
            source=source,
            comment=comment or '',
            sub_category=sub_category or '',
            row_number=row_number,
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
        from_row = self.append_transaction_row(
            [date, -abs_amt, from_source, note, 'Exchange (self)']
        )
        to_row = self.append_transaction_row(
            [date, abs_amt, to_source, note, 'Exchange (self)']
        )
        db_writer.save_transactions(
            [
                {
                    'date': date,
                    'change': -abs_amt,
                    'source': from_source,
                    'comment': note,
                    'sub_category': 'Exchange (self)',
                    'row_number': from_row,
                },
                {
                    'date': date,
                    'change': abs_amt,
                    'source': to_source,
                    'comment': note,
                    'sub_category': 'Exchange (self)',
                    'row_number': to_row,
                },
            ],
            user=self.user,
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
        tx_row_numbers = self.append_rows(
            settings.TRANSACTIONS_TABLE,
            RECEIPT_TX_COLUMNS,
            [
                [date, -s['amount'], s['source'], comment_text, sub_category, receipt_id]
                for s in normalized_sources
            ],
        )

        db_writer.save_receipt_bundle(
            user=self.user,
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
                    'row_number': tx_row_numbers[i],
                }
                for i, s in enumerate(normalized_sources)
            ],
        )

        return {
            'receiptId': receipt_id,
            'total': total,
            'items': len(normalized_items),
            'transactions': len(normalized_sources),
        }

    def buy_giftcard(
        self,
        *,
        shop: str,
        date: str,
        balance: Any,
        source: str,
    ) -> dict:
        shop_name = (shop or '').strip()
        payment_source = (source or '').strip()
        if not date:
            raise SheetsError('Date is required')
        if not shop_name:
            raise SheetsError('Shop is required')
        if not payment_source:
            raise SheetsError('Source is required')
        if payment_source == GIFTCARD_SOURCE_NAME:
            raise SheetsError('Payment source cannot be Giftcard')
        try:
            abs_amt = abs(float(balance))
        except (TypeError, ValueError):
            raise SheetsError('Invalid balance')
        if not abs_amt:
            raise SheetsError('Invalid balance')

        giftcard_id = str(uuid.uuid4())
        note = f'Buy giftcard: {shop_name}'
        sub_category = 'Giftcards'

        gc_row_numbers = self.append_rows(
            settings.GIFTCARD_TABLE,
            GIFTCARD_COLUMNS,
            [[giftcard_id, shop_name, date, abs_amt]],
        )
        tx_row_numbers = self.append_rows(
            settings.TRANSACTIONS_TABLE,
            GIFTCARD_TX_COLUMNS,
            [
                [date, -abs_amt, payment_source, note, sub_category, '', giftcard_id],
                [
                    date,
                    abs_amt,
                    GIFTCARD_SOURCE_NAME,
                    note,
                    sub_category,
                    '',
                    giftcard_id,
                ],
            ],
        )

        db_writer.save_giftcard_purchase(
            user=self.user,
            giftcard_id=giftcard_id,
            shop=shop_name,
            date=date,
            balance=abs_amt,
            row_number=gc_row_numbers[0],
            transactions=[
                {
                    'date': date,
                    'change': -abs_amt,
                    'source': payment_source,
                    'comment': note,
                    'sub_category': sub_category,
                    'row_number': tx_row_numbers[0],
                },
                {
                    'date': date,
                    'change': abs_amt,
                    'source': GIFTCARD_SOURCE_NAME,
                    'comment': note,
                    'sub_category': sub_category,
                    'row_number': tx_row_numbers[1],
                },
            ],
        )
        return {
            'giftcardId': giftcard_id,
            'shop': shop_name,
            'date': date,
            'balance': abs_amt,
            'transactions': 2,
        }

    def use_giftcard(
        self,
        *,
        giftcard_id: str,
        amount: Any,
        comment: str = '',
        sub_category: str = '',
    ) -> dict:
        from finance.models import Giftcard

        gid = str(giftcard_id or '').strip()
        if not gid:
            raise SheetsError('Giftcard ID is required')
        category = (sub_category or '').strip()
        if not category:
            raise SheetsError('Sub category is required')
        try:
            abs_amt = abs(float(amount))
        except (TypeError, ValueError):
            raise SheetsError('Invalid amount')
        if not abs_amt:
            raise SheetsError('Invalid amount')

        try:
            card = Giftcard.objects.get(pk=gid, user=self.user)
        except (Giftcard.DoesNotExist, ValueError) as exc:
            raise SheetsError('Giftcard not found', status=404) from exc

        current = float(card.balance)
        if abs_amt > current + 0.009:
            raise SheetsError(
                f'Amount ({abs_amt}) exceeds giftcard balance ({current})'
            )

        new_balance = round((current - abs_amt) * 100) / 100
        note = (comment or '').strip() or f'Use giftcard: {card.shop}'
        date = date_cls.today().isoformat()

        tx_row_numbers = self.append_rows(
            settings.TRANSACTIONS_TABLE,
            GIFTCARD_TX_COLUMNS,
            [[date, -abs_amt, GIFTCARD_SOURCE_NAME, note, category, '', gid]],
        )
        self.update_table_cell_at_row(
            settings.GIFTCARD_TABLE,
            sheet_row=card.row_number,
            update_column='Balance',
            new_value=new_balance,
        )

        db_writer.save_giftcard_use(
            user=self.user,
            giftcard_id=gid,
            new_balance=new_balance,
            date=date,
            change=-abs_amt,
            comment=note,
            sub_category=category,
            row_number=tx_row_numbers[0],
        )
        return {
            'giftcardId': gid,
            'amount': abs_amt,
            'balance': new_balance,
            'transactions': 1,
        }
