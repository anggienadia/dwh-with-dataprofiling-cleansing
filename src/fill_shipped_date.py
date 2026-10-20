from pathlib import Path
import csv

project_dir = Path(__file__).resolve().parent.parent
input_file = Path(r"C:\1.UNUD\Semester 3\Pangdat\dwh-with-dataprofiling-cleansing\data\staging_dirty\order_transactions_dirty_1M.csv")
output_file = Path(r"C:\1.UNUD\Semester 3\Pangdat\dwh-with-dataprofiling-cleansing\data\staging_dirty\order_transactions_filled.csv")

filled_count = 0

with input_file.open("r", newline="", encoding="utf-8-sig") as source, \
     output_file.open("w", newline="", encoding="utf-8-sig") as destination:

    reader = csv.DictReader(source)

    if not reader.fieldnames or "shipped_date" not in reader.fieldnames:
        raise ValueError("Kolom 'shipped_date' tidak ditemukan.")

    writer = csv.DictWriter(destination, fieldnames=reader.fieldnames)
    writer.writeheader()

    for row in reader:
        if not (row.get("shipped_date") or "").strip():
            replacement = (row.get("required_date") or "").strip()
            if not replacement:
                raise ValueError(
                    f"order_id={row.get('order_id')} juga tidak memiliki required_date."
                )

            row["shipped_date"] = replacement
            filled_count += 1

        writer.writerow(row)

print(f"Baris yang diisi: {filled_count:,}")
print(f"File hasil: {output_file}")