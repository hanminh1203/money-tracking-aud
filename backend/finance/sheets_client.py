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

TRANSACTION_ID_COLUMN = 'Transaction ID'
INPUT_COLUMNS = [
    TRANSACTION_ID_COLUMN,
    'Date',
    'Change',
    'Source',
    'Comment',
    'Sub category',
]
RECEIPT_COLUMNS = ['Receipt ID', 'Date', 'Total']
RECEIPT_ITEM_COLUMNS = ['Receipt Item ID', 'Receipt ID', 'Name', 'Amount', 'Unit', 'Money']
RECEIPT_TX_COLUMNS = [
    TRANSACTION_ID_COLUMN,
    'Date',
    'Change',
    'Source',
    'Comment',
    'Sub category',
    'Receipt ID',
]
GIFTCARD_COLUMNS = ['Giftcard ID', 'Shop', 'Date', 'Balance']
PRODUCT_COLUMNS = ['Product ID', 'Name']
PRODUCT_ITEM_COLUMNS = [
    'Product Item ID',
    'Product ID',
    'Price',
    'Transaction ID',
    'Receipt Item ID',
]
# Giftcard ID sits after Receipt ID so columns stay contiguous in the sheet table.
GIFTCARD_TX_COLUMNS = [
    TRANSACTION_ID_COLUMN,
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
    'products': {},
    'product_items': {
        'Price': EXPORT_AUD_CURRENCY,
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
            'products',
            'product_items',
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
        """Read user-owned mirror tables."""
        tx_table = self.get_table(settings.TRANSACTIONS_TABLE)
        receipt_table = self.get_table(settings.RECEIPT_TABLE)
        items_table = self.get_table(settings.RECEIPT_ITEMS_TABLE)
        giftcard_table = self.get_table(settings.GIFTCARD_TABLE)
        product_table = self.get_table(settings.PRODUCT_TABLE)
        product_items_table = self.get_table(settings.PRODUCT_ITEMS_TABLE)
        (
            tx_vals,
            receipt_vals,
            item_vals,
            giftcard_vals,
            product_vals,
            product_item_vals,
        ) = self.batch_get_values(
            [
                self.data_range_a1(tx_table),
                self.data_range_a1(receipt_table),
                self.data_range_a1(items_table),
                self.data_range_a1(giftcard_table),
                self.data_range_a1(product_table),
                self.data_range_a1(product_items_table),
            ]
        )
        return {
            'transactions': self._rows_as_dicts(tx_table, tx_vals),
            'receipts': self._rows_as_dicts(receipt_table, receipt_vals),
            'receipt_items': self._rows_as_dicts(items_table, item_vals),
            'giftcards': self._rows_as_dicts(giftcard_table, giftcard_vals),
            'products': self._rows_as_dicts(product_table, product_vals),
            'product_items': self._rows_as_dicts(product_items_table, product_item_vals),
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

    def find_matching_sheet_rows(
        self,
        table_name: str,
        *,
        match_column: str,
        match_value: str,
    ) -> list[int]:
        """Return 1-based sheet row numbers whose column equals match_value."""
        table = self.get_table(table_name)
        headers = [c['name'] for c in table['columns']]
        match_idx = self.find_col(headers, rf'^{re.escape(match_column)}$')
        if match_idx < 0:
            raise SheetsError(f'Column "{match_column}" not found in table "{table_name}"')

        values = self.get_values(self.data_range_a1(table))
        start_row = table['range']['startRowIndex'] + 2
        rows: list[int] = []
        for i, row in enumerate(values):
            cell = row[match_idx] if match_idx < len(row) else None
            if str(cell or '').strip() == str(match_value).strip():
                rows.append(start_row + i)
        return rows

    def update_table_row_at(
        self,
        table_name: str,
        *,
        sheet_row: int,
        values_by_column: dict[str, Any],
    ) -> None:
        """Update multiple cells in a sheet table row in one batch request."""
        if not values_by_column:
            return
        table = self.get_table(table_name)
        data = []
        for name, value in values_by_column.items():
            col = next((c for c in table['columns'] if c['name'] == name), None)
            if not col:
                raise SheetsError(f'Column "{name}" not found in table "{table_name}"')
            col_letter = column_letter(col['index'])
            a1 = f"{quote_sheet_title(table['sheetTitle'])}!{col_letter}{int(sheet_row)}"
            data.append({'range': a1, 'values': [[value]]})
        self.request(
            '/values:batchUpdate',
            method='POST',
            json_body={
                'valueInputOption': 'USER_ENTERED',
                'data': data,
            },
        )

    def delete_table_rows_at(self, table_name: str, sheet_rows: list[int]) -> None:
        """Delete table cells for the given 1-based sheet rows, shifting remaining cells up."""
        if not sheet_rows:
            return
        table = self.get_table(table_name)
        rng = table['range']
        sheet_id = table['sheetId']
        requests = []
        for row in sorted({int(r) for r in sheet_rows}, reverse=True):
            requests.append(
                {
                    'deleteRange': {
                        'range': {
                            'sheetId': sheet_id,
                            'startRowIndex': row - 1,
                            'endRowIndex': row,
                            'startColumnIndex': rng['startColumnIndex'],
                            'endColumnIndex': rng['endColumnIndex'],
                        },
                        'shiftDimension': 'ROWS',
                    }
                }
            )
        self.request(':batchUpdate', method='POST', json_body={'requests': requests})
        self._tables_cache = None

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
        transaction_id = str(uuid.uuid4())
        row_number = self.append_transaction_row(
            [transaction_id, date, signed, source, comment or '', sub_category or '']
        )
        db_writer.save_transaction(
            user=self.user,
            date=date,
            change=signed,
            source=source,
            comment=comment or '',
            sub_category=sub_category or '',
            row_number=row_number,
            transaction_id=transaction_id,
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
        from_tx_id = str(uuid.uuid4())
        to_tx_id = str(uuid.uuid4())
        from_row = self.append_transaction_row(
            [from_tx_id, date, -abs_amt, from_source, note, 'Exchange (self)']
        )
        to_row = self.append_transaction_row(
            [to_tx_id, date, abs_amt, to_source, note, 'Exchange (self)']
        )
        db_writer.save_transactions(
            [
                {
                    'transaction_id': from_tx_id,
                    'date': date,
                    'change': -abs_amt,
                    'source': from_source,
                    'comment': note,
                    'sub_category': 'Exchange (self)',
                    'row_number': from_row,
                },
                {
                    'transaction_id': to_tx_id,
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
            item_id = str(it.get('id') or '').strip() or str(uuid.uuid4())
            normalized_items.append(
                {
                    'id': item_id,
                    'name': name,
                    'amount': amount,
                    'unit': unit,
                    'money': money,
                }
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
                [it['id'], receipt_id, it['name'], it['amount'], it['unit'], it['money']]
                for it in normalized_items
            ],
        )
        tx_specs = [
            (str(uuid.uuid4()), s) for s in normalized_sources
        ]
        tx_row_numbers = self.append_rows(
            settings.TRANSACTIONS_TABLE,
            RECEIPT_TX_COLUMNS,
            [
                [
                    tx_id,
                    date,
                    -s['amount'],
                    s['source'],
                    comment_text,
                    sub_category,
                    receipt_id,
                ]
                for tx_id, s in tx_specs
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
                    'transaction_id': tx_id,
                    'date': date,
                    'change': -s['amount'],
                    'source': s['source'],
                    'comment': comment_text,
                    'sub_category': sub_category,
                    'row_number': tx_row_numbers[i],
                }
                for i, (tx_id, s) in enumerate(tx_specs)
            ],
        )

        return {
            'receiptId': receipt_id,
            'total': total,
            'items': len(normalized_items),
            'transactions': len(normalized_sources),
        }

    def update_transaction(
        self,
        transaction_id: str,
        *,
        date: str,
        amount: Any,
        type: str,
        source: str,
        sub_category: str = '',
        comment: str = '',
        items: list[dict] | None = None,
    ) -> dict:
        from django.core.exceptions import ValidationError
        from finance.models import Transaction

        tid = str(transaction_id or '').strip()
        if not tid:
            raise SheetsError('Transaction ID is required')
        if not date:
            raise SheetsError('Date is required')
        payment_source = str(source or '').strip()
        if not payment_source:
            raise SheetsError('Source is required')
        try:
            abs_amt = abs(float(amount))
        except (TypeError, ValueError):
            raise SheetsError('Invalid amount')
        if not abs_amt:
            raise SheetsError('Invalid amount')

        tx_type = str(type or '').strip()
        if tx_type not in ('Expense', 'Income'):
            raise SheetsError('Type must be Expense or Income')
        signed = -abs_amt if tx_type == 'Expense' else abs_amt
        category = str(sub_category or '').strip()
        note = str(comment or '')

        try:
            tx = (
                Transaction.objects.filter(user=self.user)
                .select_related('receipt')
                .prefetch_related('receipt__transactions')
                .get(pk=tid)
            )
        except (Transaction.DoesNotExist, ValueError, ValidationError) as exc:
            raise SheetsError('Transaction not found', status=404) from exc

        normalized_items = None
        total = None
        siblings: list = []
        if tx.receipt_id:
            if items is None:
                raise SheetsError('items are required for a receipt-linked transaction')
            normalized_items = []
            for i, it in enumerate(items):
                name = str(it.get('name') or '').strip()
                raw_amount = it.get('amount')
                try:
                    item_amount = float(raw_amount) if raw_amount not in (None, '') else 0.0
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
                item_id = str(it.get('id') or '').strip() or str(uuid.uuid4())
                normalized_items.append(
                    {
                        'id': item_id,
                        'name': name,
                        'amount': item_amount,
                        'unit': unit,
                        'money': money,
                    }
                )
            if not normalized_items:
                raise SheetsError('At least one item is required')
            total = round(sum(it['money'] for it in normalized_items) * 100) / 100
            siblings = [s for s in tx.receipt.transactions.all() if s.id != tx.id]
            sibling_total = round(sum(abs(float(s.change)) for s in siblings) * 100) / 100
            if abs(total - (abs_amt + sibling_total)) > 0.009:
                raise SheetsError(
                    f'Source amounts ({round((abs_amt + sibling_total) * 100) / 100}) '
                    f'must equal items total ({total})'
                )
        elif items:
            raise SheetsError('This transaction is not linked to a receipt')

        self.update_table_row_at(
            settings.TRANSACTIONS_TABLE,
            sheet_row=tx.row_number,
            values_by_column={
                'Date': date,
                'Change': signed,
                'Source': payment_source,
                'Comment': note,
                'Sub category': category,
            },
        )

        for sibling in siblings:
            self.update_table_row_at(
                settings.TRANSACTIONS_TABLE,
                sheet_row=sibling.row_number,
                values_by_column={
                    'Date': date,
                    'Comment': note,
                    'Sub category': category,
                },
            )

        if tx.receipt_id:
            receipt_rows = self.find_matching_sheet_rows(
                settings.RECEIPT_TABLE,
                match_column='Receipt ID',
                match_value=str(tx.receipt_id),
            )
            if not receipt_rows:
                raise SheetsError('Receipt not found in spreadsheet')
            self.update_table_row_at(
                settings.RECEIPT_TABLE,
                sheet_row=receipt_rows[0],
                values_by_column={'Date': date, 'Total': total},
            )

            item_rows = self.find_matching_sheet_rows(
                settings.RECEIPT_ITEMS_TABLE,
                match_column='Receipt ID',
                match_value=str(tx.receipt_id),
            )
            rid = str(tx.receipt_id)
            overlapping = min(len(item_rows), len(normalized_items or []))
            for i in range(overlapping):
                it = normalized_items[i]
                item_id = str(it.get('id') or '').strip() or str(uuid.uuid4())
                it['id'] = item_id
                self.update_table_row_at(
                    settings.RECEIPT_ITEMS_TABLE,
                    sheet_row=item_rows[i],
                    values_by_column={
                        'Receipt Item ID': item_id,
                        'Receipt ID': rid,
                        'Name': it['name'],
                        'Amount': it['amount'],
                        'Unit': it['unit'],
                        'Money': it['money'],
                    },
                )
            extra_new = (normalized_items or [])[overlapping:]
            if extra_new:
                self.append_rows(
                    settings.RECEIPT_ITEMS_TABLE,
                    RECEIPT_ITEM_COLUMNS,
                    [
                        [
                            str(it.get('id') or uuid.uuid4()),
                            rid,
                            it['name'],
                            it['amount'],
                            it['unit'],
                            it['money'],
                        ]
                        for it in extra_new
                    ],
                )
            extra_old = item_rows[overlapping:]
            if extra_old:
                self.delete_table_rows_at(settings.RECEIPT_ITEMS_TABLE, extra_old)

        db_writer.update_transaction_detail(
            user=self.user,
            transaction=tx,
            date=date,
            change=signed,
            source=payment_source,
            comment=note,
            sub_category=category,
            receipt_total=total,
            items=normalized_items,
            sibling_updates=siblings,
        )
        return {
            'id': str(tx.id),
            'updated': 1,
            'receiptUpdated': bool(tx.receipt_id),
            'items': len(normalized_items or []),
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
        debit_tx_id = str(uuid.uuid4())
        credit_tx_id = str(uuid.uuid4())
        tx_row_numbers = self.append_rows(
            settings.TRANSACTIONS_TABLE,
            GIFTCARD_TX_COLUMNS,
            [
                [
                    debit_tx_id,
                    date,
                    -abs_amt,
                    payment_source,
                    note,
                    sub_category,
                    '',
                    giftcard_id,
                ],
                [
                    credit_tx_id,
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
                    'transaction_id': debit_tx_id,
                    'date': date,
                    'change': -abs_amt,
                    'source': payment_source,
                    'comment': note,
                    'sub_category': sub_category,
                    'row_number': tx_row_numbers[0],
                },
                {
                    'transaction_id': credit_tx_id,
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

        transaction_id = str(uuid.uuid4())
        tx_row_numbers = self.append_rows(
            settings.TRANSACTIONS_TABLE,
            GIFTCARD_TX_COLUMNS,
            [[transaction_id, date, -abs_amt, GIFTCARD_SOURCE_NAME, note, category, '', gid]],
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
            transaction_id=transaction_id,
        )
        return {
            'giftcardId': gid,
            'amount': abs_amt,
            'balance': new_balance,
            'transactions': 1,
        }

    def add_product(self, *, name: str) -> dict:
        product_name = str(name or '').strip()
        if not product_name:
            raise SheetsError('Name is required')
        product_id = str(uuid.uuid4())
        self.append_rows(
            settings.PRODUCT_TABLE,
            PRODUCT_COLUMNS,
            [[product_id, product_name]],
        )
        db_writer.save_product(user=self.user, product_id=product_id, name=product_name)
        return {'productId': product_id, 'name': product_name}

    def update_product(self, *, product_id: str, name: str) -> dict:
        pid = str(product_id or '').strip()
        if not pid:
            raise SheetsError('Product ID is required')
        product_name = str(name or '').strip()
        if not product_name:
            raise SheetsError('Name is required')
        rows = self.find_matching_sheet_rows(
            settings.PRODUCT_TABLE,
            match_column='Product ID',
            match_value=pid,
        )
        if not rows:
            raise SheetsError('Product not found', status=404)
        self.update_table_row_at(
            settings.PRODUCT_TABLE,
            sheet_row=rows[0],
            values_by_column={'Name': product_name},
        )
        db_writer.update_product(user=self.user, product_id=pid, name=product_name)
        return {'productId': pid, 'name': product_name}

    def delete_product(self, *, product_id: str) -> dict:
        from finance.models import Product, ProductItem

        pid = str(product_id or '').strip()
        if not pid:
            raise SheetsError('Product ID is required')
        try:
            product = Product.objects.get(pk=pid, user=self.user)
        except (Product.DoesNotExist, ValueError) as exc:
            raise SheetsError('Product not found', status=404) from exc

        item_rows = self.find_matching_sheet_rows(
            settings.PRODUCT_ITEMS_TABLE,
            match_column='Product ID',
            match_value=pid,
        )
        if item_rows:
            self.delete_table_rows_at(settings.PRODUCT_ITEMS_TABLE, item_rows)

        product_rows = self.find_matching_sheet_rows(
            settings.PRODUCT_TABLE,
            match_column='Product ID',
            match_value=pid,
        )
        if not product_rows:
            raise SheetsError('Product not found in spreadsheet', status=404)
        self.delete_table_rows_at(settings.PRODUCT_TABLE, product_rows)

        ProductItem.objects.filter(user=self.user, product=product).delete()
        db_writer.delete_product(user=self.user, product_id=pid)
        return {'productId': pid, 'deleted': True}

    def add_product_item(
        self,
        *,
        product_id: str,
        transaction_id: str | None = None,
        receipt_item_id: str | None = None,
        price: Any = None,
    ) -> dict:
        from finance.models import Product, ReceiptItem, Transaction

        pid = str(product_id or '').strip()
        if not pid:
            raise SheetsError('Product ID is required')
        tx_id = str(transaction_id or '').strip() or None
        ri_id = str(receipt_item_id or '').strip() or None
        if bool(tx_id) == bool(ri_id):
            raise SheetsError('Link to transaction or receipt item is required')

        try:
            Product.objects.get(pk=pid, user=self.user)
        except (Product.DoesNotExist, ValueError) as exc:
            raise SheetsError('Product not found', status=404) from exc

        tx_sheet_value = ''
        sheet_price = ''
        if tx_id:
            try:
                tx = Transaction.objects.get(pk=tx_id, user=self.user)
            except (Transaction.DoesNotExist, ValueError) as exc:
                raise SheetsError('Transaction not found', status=404) from exc
            if price is None:
                raise SheetsError('Price is required when linking a transaction')
            try:
                sheet_price = abs(float(price))
            except (TypeError, ValueError):
                raise SheetsError('Invalid price')
            if not sheet_price:
                raise SheetsError('Invalid price')
            tx_sheet_value = str(tx.id)
        else:
            try:
                ReceiptItem.objects.get(pk=ri_id, user=self.user)
            except (ReceiptItem.DoesNotExist, ValueError) as exc:
                raise SheetsError('Receipt item not found', status=404) from exc
            if price is not None:
                try:
                    sheet_price = abs(float(price))
                except (TypeError, ValueError):
                    raise SheetsError('Invalid price')

        product_item_id = str(uuid.uuid4())
        self.append_rows(
            settings.PRODUCT_ITEMS_TABLE,
            PRODUCT_ITEM_COLUMNS,
            [[product_item_id, pid, sheet_price, tx_sheet_value, ri_id or '']],
        )
        db_writer.save_product_item(
            user=self.user,
            product_item_id=product_item_id,
            product_id=pid,
            price=sheet_price if sheet_price != '' else None,
            transaction_id=tx_id,
            receipt_item_id=ri_id,
        )
        return {
            'productItemId': product_item_id,
            'productId': pid,
            'transactionId': tx_id,
            'receiptItemId': ri_id,
            'price': sheet_price if sheet_price != '' else None,
        }

    def delete_product_item(self, *, product_item_id: str) -> dict:
        from finance.models import ProductItem

        pi_id = str(product_item_id or '').strip()
        if not pi_id:
            raise SheetsError('Product Item ID is required')
        try:
            ProductItem.objects.get(pk=pi_id, user=self.user)
        except (ProductItem.DoesNotExist, ValueError) as exc:
            raise SheetsError('Product item not found', status=404) from exc

        rows = self.find_matching_sheet_rows(
            settings.PRODUCT_ITEMS_TABLE,
            match_column='Product Item ID',
            match_value=pi_id,
        )
        if rows:
            self.delete_table_rows_at(settings.PRODUCT_ITEMS_TABLE, rows)
        db_writer.delete_product_item(user=self.user, product_item_id=pi_id)
        return {'productItemId': pi_id, 'deleted': True}
