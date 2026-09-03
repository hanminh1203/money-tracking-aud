# Google Sheet migration: Payment tables

After upgrading to the payment restructure, update your finance spreadsheet:

1. Add a **Payment** table with columns: `Payment ID`, `Transaction ID`, `Source`, `Amount`.
2. Add a **GiftcardPayment** table with columns: `Giftcard Payment ID`, `Transaction ID`, `Giftcard ID`, `Amount`.
3. In **Transactions**, remove the `Source` and `Giftcard ID` columns. Keep: `Transaction ID`, `Date`, `Change`, `Comment`, `Sub category`, `Receipt ID`.
4. For each existing transaction row, create payment rows that sum to `abs(Change)` (one `Payment` per former source; giftcard uses become `GiftcardPayment` rows).
5. Run **Management → Sync** to verify fingerprints match.

Export from Management can generate a workbook with the new layout if you prefer to migrate from Postgres.
