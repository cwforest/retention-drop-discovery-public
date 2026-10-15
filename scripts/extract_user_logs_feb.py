"""user_logs.csv(v1, 30.5GB)에서 2017년 2월만 걸러 parquet으로 만듦.

왜 필요한가:
  습관 변수(D)를 3/1~3/7 7일로만 재면 활동일 수가 최댓값에 36%나 몰리고(천장 효과),
  측정 기간에 활동이 없어 아예 못 재는 유저가 기준일 행의 6.1%나 됨. 그 집단은 기간이 갈수록
  D1이 11%p 올라가 기준선을 흔듦. 습관 창을 2월 한 달(28일 = 정확히 4주)로 늘리면 이 문제가
  크게 줄고, 이용 주기 유형처럼 7일로는 불안정하던 변수도 쓸 수 있게 됨.

왜 통째로 안 읽나:
  원본이 30.5GB인데 디스크 여유가 10GB 미만임. 한 번에 올리면 메모리도 40GB로는 부족함.
  그래서 pyarrow로 블록 단위로 흘려 읽으면서 2017-02 행만 골라 바로 parquet에 써 넣음.
  최대 메모리 사용은 블록 하나(기본 256MB) 수준임.

쓰는 법 (저장소 루트에서):
  python scripts/extract_user_logs_feb.py
  python scripts/extract_user_logs_feb.py --force      # 이미 있어도 다시 만듦
"""
import argparse
import os
import time

import psutil
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SRC = os.path.join(DATA, "user_logs.csv")
OUT = os.path.join(DATA, "user_logs_feb2017.parquet")

LO, HI = 20170201, 20170228          # 2017년 2월 (v1의 마지막 달임)
#   1월까지 꺼내 두면 습관 창을 더 늘리거나 월말 효과(1/31 vs 2/28)를 볼 수 있으나,
#   디스크 여유가 9GB뿐이라 지금은 2월만 꺼냄. 필요해지면 LO를 20170101로 바꿔 다시 돌리면 됨.
BLOCK = 24 << 20                     # 한 번에 읽는 크기 24MB
#   256MB로 두면 pyarrow가 블록을 여러 개 미리 읽어 12GB까지 먹음. 그러면 램이 모자라
#   페이지파일이 부풀어 디스크를 다 써버림(실제로 한 번 실패했음). 작게 잡아도 속도는 비슷함.
FLUSH = 2_000_000                    # 걸러낸 행이 이만큼 모이면 한 번에 써서 row group 수를 줄임

# user_logs_v2.parquet과 같은 타입으로 맞춤 — 나중에 3월과 이어 붙여 쓰기 위함임
TYPES = {"msno": pa.string(), "date": pa.int32(), "num_25": pa.int32(), "num_50": pa.int32(),
         "num_75": pa.int32(), "num_985": pa.int32(), "num_100": pa.int32(),
         "num_unq": pa.int32(), "total_secs": pa.float64()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(SRC):
        raise SystemExit(f"원본이 없음: {SRC}")
    if os.path.exists(OUT) and not args.force:
        raise SystemExit(f"이미 있음: {OUT}  (다시 만들려면 --force)")

    total_gb = os.path.getsize(SRC) / 2 ** 30
    print(f"원본: {SRC}  ({total_gb:.1f}GB)")
    print(f"거를 범위: {LO} ~ {HI}\n")

    reader = pacsv.open_csv(
        SRC,
        read_options=pacsv.ReadOptions(block_size=BLOCK),
        convert_options=pacsv.ConvertOptions(column_types=TYPES))

    writer = None
    buf, n_buf = [], 0
    t0 = time.time()
    n_in = n_out = n_block = 0
    dmin, dmax = None, None
    proc = psutil.Process()

    def flush():
        """모아둔 배치를 한 번에 써 넣음"""
        nonlocal writer, buf, n_buf
        if not buf:
            return
        t = pa.Table.from_batches(buf)
        if writer is None:
            writer = pq.ParquetWriter(OUT, t.schema, compression="zstd")
        writer.write_table(t)
        buf, n_buf = [], 0

    try:
        for batch in reader:
            n_in += batch.num_rows
            n_block += 1
            d = batch.column("date")
            sel = batch.filter(pc.and_(pc.greater_equal(d, LO), pc.less_equal(d, HI)))
            if sel.num_rows:
                buf.append(sel)
                n_buf += sel.num_rows
                n_out += sel.num_rows
                if n_buf >= FLUSH:
                    flush()
            # v1이 어느 날짜까지 담고 있는지도 같이 확인함
            lo, hi = pc.min_max(d).as_py().values()
            dmin = lo if dmin is None else min(dmin, lo)
            dmax = hi if dmax is None else max(dmax, hi)
            if n_block % 200 == 0:
                el, done = time.time() - t0, n_block * BLOCK / 2 ** 30
                free = psutil.disk_usage(DATA).free / 2 ** 30
                print(f"  {done:6.1f}GB / {total_gb:.1f}GB  읽은 행 {n_in:>12,}  "
                      f"골라낸 행 {n_out:>10,}  {el/60:4.1f}분  "
                      f"(남은 약 {el/max(done,1e-9)*(total_gb-done)/60:.0f}분)  "
                      f"램 {proc.memory_info().rss/2**30:.1f}GB  디스크 여유 {free:.1f}GB", flush=True)
                if free < 1.5:
                    raise SystemExit("디스크 여유가 1.5GB 밑으로 떨어져 중단함")
        flush()
    finally:
        if writer is not None:
            writer.close()

    el = time.time() - t0
    print(f"\n읽은 행 {n_in:,}  →  2017-02 행 {n_out:,} ({n_out/n_in:.2%})")
    print(f"v1 전체 날짜 범위: {dmin} ~ {dmax}")
    print(f"저장: {OUT}  ({os.path.getsize(OUT)/2**20:,.0f}MB)")
    print(f"걸린 시간: {el/60:.1f}분")


if __name__ == "__main__":
    main()
