"""transactions.csv(v1, ~2017-02-28)와 transactions_v2.csv(v2, 3월 위주)를 합쳐
   data/transactions_all.parquet 을 만듦.

왜 필요한가:
  v2만 쓰면 과거 결제 이력이 거의 없음. 3월에 30일 월 구독을 결제한 유저 100만 명 중
  2월 기록이 남아 있는 사람은 8.6%뿐이라, 기준일 t 이전 구독 상태를 알 수 없는 행이
  정상 기간(3/8~3/14)에서 약 48%에 달함. v1을 더하면 이 공백이 채워짐.

쓰는 법 (저장소 루트에서):
  python scripts/merge_transactions.py

  data/ 에 transactions.csv 와 transactions_v2.csv 가 있어야 함.
  이미 만들어진 parquet은 건너뜀. 다시 만들려면 --force 를 붙임.
"""
import argparse
import os
import sys
import time

import numpy as np
import pandas as pd

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

DTYPE = {
    "msno": "string[pyarrow]",   # object 대신 arrow 문자열 — 2천만 행에서 메모리가 몇 배 차이남
    "payment_method_id": "int32", "payment_plan_days": "int32",
    "plan_list_price": "int32", "actual_amount_paid": "int32", "is_auto_renew": "int32",
    "transaction_date": "int32", "membership_expire_date": "int32", "is_cancel": "int32",
}
# 같은 거래가 두 파일에 겹쳐 들어 있을 수 있어 아래 조합으로 중복을 판정함
KEY = ["msno", "transaction_date", "membership_expire_date",
       "payment_method_id", "payment_plan_days", "actual_amount_paid", "is_cancel"]

OUT = os.path.join(DATA, "transactions_all.parquet")
CHUNK = 2_000_000


def collect(name, parts, keys):
    """CSV를 청크로 읽어 모으면서 중복 판정용 키 해시도 같이 쌓음. 파일이 없으면 0"""
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        return 0
    n = 0
    for chunk in pd.read_csv(path, dtype=DTYPE, chunksize=CHUNK):
        parts.append(chunk)
        keys.append(pd.util.hash_pandas_object(chunk[KEY], index=False).to_numpy())
        n += len(chunk)
    print("  %s: %s행" % (name, format(n, ",")))
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="이미 있어도 다시 만듦")
    args = ap.parse_args()

    if os.path.exists(OUT) and not args.force:
        print("이미 있음: %s  (다시 만들려면 --force)" % OUT)
        return 0

    t0 = time.time()
    print("읽는 중...")
    parts, keys = [], []
    n1 = collect("transactions.csv", parts, keys)
    n2 = collect("transactions_v2.csv", parts, keys)
    if n2 == 0:
        print("오류: data/transactions_v2.csv 가 없음", file=sys.stderr)
        return 1
    if n1 == 0:
        print("오류: data/transactions.csv (v1) 가 없음 — Kaggle 데이터 페이지에서 받을 것", file=sys.stderr)
        return 1

    # 중복 제거: 키 해시의 첫 등장만 남김 (넓은 표 전체를 비교하지 않아 메모리를 아낌)
    h = np.concatenate(keys)
    del keys
    _, first = np.unique(h, return_index=True)
    keep = np.zeros(len(h), dtype=bool)
    keep[first] = True
    del h, first
    print("\n합계 %s행 → 중복 제거 후 %s행 (%s행 제거)"
          % (format(n1 + n2, ","), format(int(keep.sum()), ","), format(int((~keep).sum()), ",")))

    df = pd.concat(parts, ignore_index=True)
    del parts
    df = df[keep].reset_index(drop=True)
    del keep

    df = df.sort_values(["msno", "transaction_date"], ignore_index=True)
    df.to_parquet(OUT, engine="pyarrow", compression="zstd", index=False)

    # ── 검증 ────────────────────────────────────────────────────────────
    print("\n저장: %s  (%.0fMB, %.0f초)" % (OUT, os.path.getsize(OUT) / 1e6, time.time() - t0))
    print("\n[검증]")
    print("  행 수      : %s" % format(len(df), ","))
    print("  고유 유저  : %s" % format(df.msno.nunique(), ","))
    print("  날짜 범위  : %d ~ %d" % (df.transaction_date.min(), df.transaction_date.max()))
    print("  결측       : %d건" % int(df.isna().sum().sum()))
    n = df.groupby("msno").size()
    print("  유저당 거래: 평균 %.2f건, 중앙값 %d건, 1건뿐 %.1f%%"
          % (n.mean(), int(n.median()), 100 * (n == 1).mean()))
    ym = (df.transaction_date // 100).value_counts().sort_index()
    print("  연-월 분포 (상위 6):")
    for k, v in ym.sort_values(ascending=False).head(6).sort_index().items():
        print("    %d-%02d  %9s  (%.1f%%)" % (k // 100, k % 100, format(v, ","), 100 * v / len(df)))
    mar = set(df.loc[df.transaction_date >= 20170301, "msno"])
    feb = set(df.loc[(df.transaction_date >= 20170201) & (df.transaction_date <= 20170228), "msno"])
    print("  3월 결제자 중 2월 기록 보유: %.1f%%  (v2만 썼을 때 8.6%%)" % (100 * len(mar & feb) / len(mar)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
