# Google Sheet migration: Receipt owns Transaction ID

After upgrading, update your finance spreadsheet:

1. In **Receipt**, add a **Transaction ID** column (after `Receipt ID`).
2. For each receipt row, copy the matching transaction’s ID from **Transactions** (the row that previously had that receipt’s `Receipt ID`).
3. In **Transactions**, remove the **Receipt ID** column. Keep: `Transaction ID`, `Date`, `Change`, `Comment`, `Sub category`.
4. Run **Management → Sync** to verify fingerprints match.

Export from Management can generate a workbook with the new layout if you prefer to migrate from Postgres.

---

# Google Sheet migration: Payment tables

After upgrading to the payment restructure, update your finance spreadsheet:

1. Add a **Payment** table with columns: `Payment ID`, `Transaction ID`, `Source`, `Amount`.
2. Add a **GiftcardPayment** table with columns: `Giftcard Payment ID`, `Transaction ID`, `Giftcard ID`, `Amount`.
3. In **Transactions**, remove the `Source` and `Giftcard ID` columns. Keep: `Transaction ID`, `Date`, `Change`, `Comment`, `Sub category`.
4. For each existing transaction row, create payment rows that sum to `abs(Change)` (one `Payment` per former source; giftcard uses become `GiftcardPayment` rows).
5. Run **Management → Sync** to verify fingerprints match.

Export from Management can generate a workbook with the new layout if you prefer to migrate from Postgres.
