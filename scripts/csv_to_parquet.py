"""Kaggle CSV 4개를 parquet으로 변환함.

왜 필요한가:
  user_logs_v2.csv는 1,840만 줄(1.4GB)이라 pd.read_csv로 통째로 읽으면 5GB 넘게 먹음.
  parquet으로 바꿔두면 같은 데이터가 1.5GB로 들어오고, 필요한 컬럼만 골라 읽을 수도 있음.
  메모리 8GB 이하 노트북에서도 문제없이 돌아감.

쓰는 법 (저장소 루트에서):
  python scripts/csv_to_parquet.py

  data/ 폴더에 CSV 4개가 있어야 함. 받는 법은 README 참고.
  이미 만들어진 parquet은 건너뜀. 다시 만들려면 --force를 붙임.
"""
import argparse
import os
import sys
import time

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# msno는 문자열, 날짜는 YYYYMMDD 숫자라 int32로 충분함.
# int8/int16까지 줄이면 값이 범위를 넘을 때 터지므로 int32로 통일했음 (parquet 압축이 알아서 줄여줌).
# bd(나이)와 total_secs는 이상치가 크기 때문에 여기서 손대지 않고 원본 그대로 둠 — 정리는 분석 단계에서 함.
JOBS = [
    ("train_v2.csv", {
        "msno": "str", "is_churn": "int32",
    }, None),
    ("transactions_v2.csv", {
        "msno": "str", "payment_method_id": "int32", "payment_plan_days": "int32",
        "plan_list_price": "int32", "actual_amount_paid": "int32", "is_auto_renew": "int32",
        "transaction_date": "int32", "membership_expire_date": "int32", "is_cancel": "int32",
    }, None),
    ("members_v3.csv", {
        "msno": "str", "city": "int32", "bd": "int32", "gender": "str",
        "registered_via": "int32", "registration_init_time": "int32",
    }, 2_000_000),
    ("user_logs_v2.csv", {
        "msno": "str", "date": "int32", "num_25": "int32", "num_50": "int32",
        "num_75": "int32", "num_985": "int32", "num_100": "int32", "num_unq": "int32",
        "total_secs": "float64",  # float32로 줄이면 큰 값에서 정밀도가 깨짐
    }, 2_000_000),
]


def convert(src, dst, dtype, chunksize):
    """CSV 한 개를 parquet으로 바꿈. chunksize가 있으면 나눠 읽어 메모리를 아낌."""
    rows = 0
    if chunksize is None:
        df = pd.read_csv(src, dtype=dtype)
        rows = len(df)
        df.to_parquet(dst, engine="pyarrow", compression="zstd", index=False)
        return rows

    writer = None
    try:
        for chunk in pd.read_csv(src, dtype=dtype, chunksize=chunksize):
            table = pa.Table.from_pandas(chunk, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(dst, table.schema, compression="zstd")
            else:
                # 청크마다 타입 추론이 흔들릴 수 있으니 첫 청크 스키마에 맞춤
                table = table.cast(writer.schema)
            writer.write_table(table)
            rows += len(chunk)
    except BaseException:
        # 중간에 끊기면 반쪽짜리 parquet이 남아 다음 실행 때 건너뛰어 버림. 지우고 종료함.
        if writer is not None:
            writer.close()
            writer = None
        if os.path.exists(dst):
            os.remove(dst)
        raise
    finally:
        if writer is not None:
            writer.close()
    return rows


def main():
    parser = argparse.ArgumentParser(description="Kaggle CSV를 parquet으로 변환함")
    parser.add_argument("--force", action="store_true", help="이미 있는 parquet도 다시 만듦")
    args = parser.parse_args()

    if not os.path.isdir(DATA):
        sys.exit(f"data 폴더 없음: {DATA}\nKaggle에서 CSV를 받아 넣는 방법은 README 참고.")

    missing = [name for name, _, _ in JOBS if not os.path.exists(os.path.join(DATA, name))]
    if missing:
        sys.exit("CSV 없음: " + ", ".join(missing) + "\n받는 방법은 README 참고.")

    for name, dtype, chunksize in JOBS:
        src = os.path.join(DATA, name)
        dst = os.path.join(DATA, name.replace(".csv", ".parquet"))

        if os.path.exists(dst) and not args.force:
            print(f"{name:22s} 건너뜀 (이미 있음 — 다시 만들려면 --force)")
            continue

        t0 = time.time()
        rows = convert(src, dst, dtype, chunksize)
        src_mb = os.path.getsize(src) / 1024 ** 2
        dst_mb = os.path.getsize(dst) / 1024 ** 2
        print(f"{name:22s} {rows:>11,}행  {src_mb:6.0f}MB -> {dst_mb:5.0f}MB  {time.time() - t0:5.1f}초")

    print("\n완료. 노트북에서 pd.read_parquet('data/<이름>.parquet')으로 읽으면 됨.")


if __name__ == "__main__":
    main()
