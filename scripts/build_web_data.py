# -*- coding: utf-8 -*-
"""웹 페이지가 쓸 JSON 을 만듦 → docs/web/data/

페이지는 계산을 하지 않고 **미리 계산해 둔 값만** 읽어 그림. 숫자가 바뀌면 이 스크립트만
다시 돌리면 되고 HTML 은 손대지 않아도 됨.

만드는 것 — **두 창(14일·2일)을 다 만듦**. 페이지에서 눌러 전환함
  nday.json          3월 신규 유저 N-Day 리텐션 (Day 0~21) — 창과 무관해 하나뿐
  창목록.json         어느 창이 준비됐나 + 어느 것이 주 분석인가
  d1_daily_{창}.json  기준일별 D1 (3/1~3/30) — 요일·구간 포함
  groups_{창}.json    δ 슬라이더용 — 집단마다 찾음δ·보고δ 와 측정 상세
  curve_{창}.json     조건별 크기 대 보고 하한 (산점도용)
  meta_{창}.json      기간·판정선 같은 기본 숫자

읽는 결과 파일 — `하한_전체`(조건 1개) · `찾음하한_2조건`(조건 2개) · **`재시도_2조건`(9-8,
있으면 찾음하한·상한을 덮어씀)** · `무주입_조건`(크기 대 하한 산점도)

쓰는 법 (저장소 루트에서):
  python scripts/build_web_data.py
"""
import io as _io, sys as _sys
_sys.stdout = _io.TextIOWrapper(_sys.stdout.buffer, encoding='utf-8')  # 콘솔 cp949 회피용임
import json
import os
import shutil

import numpy as np
import pandas as pd

NL = chr(10)
DATA = 'data'
RES = 'results'
OUT = os.path.join('docs', 'web', 'data')
os.makedirs(OUT, exist_ok=True)

TRAIN_LAST = 14      # 학습 마지막 기준일 (3/15) — 두 창 공통임

# 창마다 다른 숫자들. 전에는 14일 값이 박혀 있어 2일 데이터에 14일 판정선·행수가 붙었음
창설정 = {
    '2일':  {'평가끝': 16, '판정선': -3.636, '유효인원': 728502,
            '평가기간': '기준일 3/16~3/17 (결과일 3/17~3/18)', '평가행': 1204768},
    '14일': {'평가끝': 28, '판정선': -7.470115027684667, '유효인원': 992683,
            '평가기간': '기준일 3/16~3/29 (결과일 3/17~3/30)', '평가행': 8407908},
}
주분석 = '2일'      # 페이지를 열면 이 창이 먼저 보임


def 쓸파일(이름, 창):
    """그 창의 결과 파일 경로. 없으면 None — 창마다 따로 쌓이므로 섞이지 않음"""
    경로 = os.path.join(RES, '{}_{}.csv'.format(이름, 창))
    return 경로 if os.path.exists(경로) else None


def 씻기(x):
    """NaN·inf 를 None 으로 바꿈. 파이썬 json 은 NaN 을 그냥 쓰는데
       JSON 표준에 없는 값이라 브라우저의 JSON.parse 가 **파일 전체를 거부함**.
       못 찾은 집단의 찾음하한이 NaN 이라 10/11 에 웹페이지가 통째로 안 뜬 적 있음"""
    if isinstance(x, dict):
        return {k: 씻기(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [씻기(v) for v in x]
    if isinstance(x, float) and (x != x or x in (float('inf'), float('-inf'))):
        return None
    return x


def 저장(이름, 값):
    with open(os.path.join(OUT, 이름), 'w', encoding='utf-8') as f:
        # allow_nan=False 로 남은 NaN 이 있으면 조용히 넘어가지 말고 터지게 함
        json.dump(씻기(값), f, ensure_ascii=False, indent=1, allow_nan=False)
    print('  {} ({:,} bytes)'.format(이름, os.path.getsize(os.path.join(OUT, 이름))))


# ── 1. 3월 신규 유저 N-Day 리텐션 ───────────────────────────────────────
def nday():
    """가입일 = Day 0. 3월에 가입하고 가입 당일 재생한 유저만.
       Day N 은 'Day N 까지 데이터가 있는 코호트' 만 분모로 씀"""
    uniq = pd.read_parquet(f'{DATA}/cache/active_users.parquet')['msno']
    z = np.load(f'{DATA}/cache/active_keys.npz')
    key_all = z['key_all']

    mem = pd.read_parquet(f'{DATA}/members_v3.parquet',
                          columns=['msno', 'registration_init_time'])
    mem = mem.set_index('msno').reindex(uniq)
    _reg = pd.to_datetime(mem['registration_init_time'].astype('Int64').astype('string'),
                          format='%Y%m%d', errors='coerce')
    reg = (_reg - pd.Timestamp('2017-03-01')).dt.days.to_numpy()

    신규 = np.where(np.isfinite(reg) & (reg >= 0) & (reg <= 30))[0]
    가입일 = reg[신규].astype('int64')
    # 가입 당일에 재생했나 (Day 0)
    있음 = np.isin(신규 * 64 + 가입일, key_all)
    신규, 가입일 = 신규[있음], 가입일[있음]
    print('  3월 가입 + 가입 당일 재생 {:,}명'.format(len(신규)))

    줄 = []
    for N in range(0, 22):
        쓸수있음 = 가입일 + N <= 30          # 3월 안에 Day N 이 들어오는 코호트만
        분모 = int(쓸수있음.sum())
        if 분모 == 0:
            continue
        돌아옴 = np.isin(신규[쓸수있음] * 64 + 가입일[쓸수있음] + N, key_all)
        줄.append({'day': N, '분모': 분모, '리텐션': round(float(돌아옴.mean()), 5)})
    return {'유저수': int(len(신규)), '점': 줄}


# ── 2. 기준일별 D1 ──────────────────────────────────────────────────────
def d1_daily(창, _통=[]):
    """실제 D1 과 기대 모델이 낸 확률 p 를 날짜별로 나란히 냄.
       둘의 차이가 곧 편차이고, 이 방법이 보는 값임.
       날짜별 값 자체는 창과 무관하므로 parquet 은 한 번만 읽고 재사용함"""
    EVAL_LAST = 창설정[창]['평가끝']
    if _통:
        m, 기대, g = _통[0]
    else:
        m, 기대, g = _읽기()
        _통.append((m, 기대, g))
    요일 = ['수', '목', '금', '토', '일', '월', '화']      # 2017-03-01 이 수요일
    줄 = []
    for d, r in g.iterrows():
        d = int(d)
        구간 = '학습' if d <= TRAIN_LAST else ('평가' if d <= EVAL_LAST else '제외')
        줄.append({'day': d,
                   '날짜': '3/{}'.format(d + 1),
                   '요일': 요일[d % 7],
                   '분모': int(r['size']),
                   'D1': round(float(r['mean']), 5),
                   '기대': round(float(기대.loc[d]), 5),
                   '구간': 구간})
    return {'점': 줄,
            '학습평균': round(float(m.loc[m['day'] <= TRAIN_LAST, 'd1'].mean()), 5),
            '평가평균': round(float(m.loc[(m['day'] > TRAIN_LAST)
                                     & (m['day'] <= EVAL_LAST), 'd1'].mean()), 5)}


def _읽기():
    m = pd.read_parquet(f'{DATA}/mart.parquet', columns=['day', 'd1'])
    pr = pd.read_parquet(f'{DATA}/pred.parquet', columns=['day', 'p'])
    assert len(m) == len(pr), '행 수가 안 맞음'
    m['p'] = pr['p'].to_numpy()
    기대 = m.groupby('day')['p'].mean()
    g = m.groupby('day')['d1'].agg(['size', 'mean'])
    return m, 기대, g


# ── 3. δ 슬라이더용 집단 ────────────────────────────────────────────────
def 두하한(g, 판정선):
    """한 집단의 (찾음δ, 보고δ) — 찾음은 Hit@3 ≥ 0.7 인 가장 작은 δ,
       보고는 정답t 가 판정선에 닿는 δ 를 직선 보간으로"""
    g = g.copy()
    g['Hit3'] = ((g['순위'] >= 1) & (g['순위'] <= 3)).astype(float)
    요약 = g.groupby('δ').agg(Hit1=('순위', lambda x: float((x == 1).mean())),
                             Hit3=('Hit3', 'mean'),
                             겹침=('최고겹침', 'mean'),
                             정답t=('정답t', 'mean'),
                             판수=('회', 'count')).reset_index()
    찾음 = 요약.loc[요약['Hit3'] >= 0.7, 'δ']
    찾음 = float(찾음.min()) if len(찾음) else None

    ds = 요약['δ'].to_numpy(dtype='float64')
    ts = 요약['정답t'].to_numpy(dtype='float64')
    기울기 = (ts[-1] - ts[0]) / (ds[-1] - ds[0])
    보고 = float(ds[0] + (판정선 - ts[0]) / 기울기) if 기울기 < 0 else None
    return 찾음, 보고, 요약


def groups(창):
    판정선 = 창설정[창]['판정선']
    묶음 = []
    경로 = 쓸파일('하한_전체', 창)
    if 경로:
        전체 = pd.read_csv(경로, encoding='utf-8-sig')
        # 집단 크기는 박아 두지 않고 그 창의 무주입 표에서 이름으로 찾음
        무경로 = 쓸파일('무주입_조건', 창)
        크기 = {}
        if 무경로:
            무 = pd.read_csv(무경로, encoding='utf-8-sig').drop_duplicates('이름')
            for _, r in 무.iterrows():
                크기[r['이름']] = (int(r['평가행']), int(r['유효인원']), round(float(r['t']), 2))
        평가행수 = 창설정[창]['평가행']
        for 이름, g in 전체.groupby('집단', sort=False):
            찾음, 보고, 요약 = 두하한(g, 판정선)
            행, 인원, t0 = 크기.get(이름, (None, None, None))
            묶음.append({'이름': 이름, '종류': '조건 1개',
                        '평가행': 행, '유효인원': 인원,
                        '비중': round(행 / 평가행수, 5) if 행 else None,
                        '희석r': None, '무주입t': t0,
                        '찾음δ': 찾음, '보고δ': round(보고, 2) if 보고 else None,
                        '측정': 요약.round(4).to_dict('records')})
        print('  조건 1개 {}개'.format(len(묶음)))
    else:
        print('  (없음) 하한_전체')

    경로2 = 쓸파일('찾음하한_2조건', 창)
    if 경로2:
        쌍 = pd.read_csv(경로2, encoding='utf-8-sig')
        평가행수 = 창설정[창]['평가행']

        # 9-8 (10/12) — 9-7 에서 못 찾은 집단을 상한 20%p 로 다시 잰 결과가 있으면 덮어씀.
        # 9-7 의 상한은 `예측 × 1.4` 뿐이라 「못 찾음」이 「끝까지 못 찾음」이 아니었음.
        # 실험 기록인 9-7 csv 는 그대로 두고 여기서 합침 — 원자료를 고치지 않으려고 그럼
        경로3 = 쓸파일('재시도_2조건', 창)
        if 경로3:
            다시 = pd.read_csv(경로3, encoding='utf-8-sig').set_index(['A', 'B'])
            고친수 = 0
            for i, r in 쌍.iterrows():
                키 = (r['A'], r['B'])
                if 키 in 다시.index:
                    그줄 = 다시.loc[키]
                    쌍.at[i, '찾음하한'] = 그줄['찾음하한']
                    쌍.at[i, '상한'] = 그줄['새상한']
                    고친수 += 1
            print('  9-8 로 {}개 갱신 (상한 20%p 로 다시 잰 것)'.format(고친수))
        for _, r in 쌍.iterrows():
            묶음.append({'이름': '{} AND {}'.format(r['A'], r['B']), '종류': '조건 2개',
                        '평가행': int(r['평가행']), '유효인원': None,
                        '비중': round(float(r['평가행']) / 평가행수, 5),
                        '희석r': round(float(r['희석r']), 4),
                        '무주입t': None,
                        # 상한까지 올려도 못 찾은 집단은 찾음하한이 비어 있음 → None
                        '찾음δ': (None if pd.isna(r['찾음하한'])
                                else round(float(r['찾음하한']), 2)),
                        '보고δ': round(float(r['보고δ예측']), 2),
                        '못찾음': bool(pd.isna(r['찾음하한'])),
                        # 못 찾은 집단은 '어디까지 심어 봤나' 를 보여줘야 말이 됨
                        '상한': (round(float(r['상한']), 2) if '상한' in r.index
                               and pd.notna(r['상한']) else None),
                        '측정': []})
        print('  조건 2개 {}개'.format(len(쌍)))
    else:
        print('  (아직 없음) 찾음하한_2조건 — 9-7 이 끝나면 다시 돌릴 것')

    # ── 조건 3개 (9-11, 10/12) ──────────────────────────────────────────
    # 여기서 처음으로 **도달(빔) 관문**이 작동함 — 15개 중 6개. 조건 2개는 0개였음.
    # 그래서 이 묶음만 '도달δ' 와 '막힘' 을 같이 실음
    경로4 = 쓸파일('찾음하한_3조건', 창)
    if 경로4:
        셋 = pd.read_csv(경로4, encoding='utf-8-sig')
        평가행수 = 창설정[창]['평가행']
        for _, r in 셋.iterrows():
            묶음.append({'이름': '{} AND {} AND {}'.format(r['A'], r['B'], r['C']),
                        '종류': '조건 3개',
                        '평가행': int(r['평가행']), '유효인원': None,
                        '비중': round(float(r['평가행']) / 평가행수, 5),
                        '희석r': round(float(r['희석r']), 4),
                        '무주입t': None,
                        '찾음δ': (None if pd.isna(r['찾음하한'])
                                else round(float(r['찾음하한']), 2)),
                        '보고δ': round(float(r['보고δ예측']), 2),
                        '도달δ': round(float(r['도달δ예측']), 2),
                        '예측δ': round(float(r['예측하한']), 2),
                        '막힘': r['무엇에막히나'],
                        '못찾음': bool(pd.isna(r['찾음하한'])),
                        '상한': (round(float(r['상한']), 2) if pd.notna(r['상한']) else None),
                        '측정': []})
        막힌수 = int((셋['무엇에막히나'] == '도달(빔)').sum())
        print('  조건 3개 {}개 (도달에 막히는 것 {}개)'.format(len(셋), 막힌수))
    else:
        print('  (아직 없음) 찾음하한_3조건 — 9-11 이 끝나면 다시 돌릴 것')
    return 묶음


# ── 4. 크기 대 보고 하한 ────────────────────────────────────────────────
def curve(창):
    경로 = 쓸파일('무주입_조건', 창)
    if not 경로:
        print('  (아직 없음) 무주입_조건 — 9-3 을 실행할 것')
        return None
    d = pd.read_csv(경로, encoding='utf-8-sig').drop_duplicates('이름')
    d = d[d['보고하한'].notna() & (d['보고하한'] > 0)]      # 음수면 log 가 nan 이 됨
    x = np.log(d['유효인원'].to_numpy())
    y = np.log(d['보고하한'].to_numpy())
    기울기, 절편 = np.polyfit(x, y, 1)
    경계 = [0, 3000, 10000, 30000, 100000, 10 ** 9]
    이름표 = ['~3천', '3천~1만', '1만~3만', '3만~10만', '10만+']
    d['크기'] = pd.cut(d['평가행'], 경계, labels=이름표)
    띠 = []
    for 칸, g in d.groupby('크기', observed=True):
        띠.append({'구간': str(칸), '개수': int(len(g)),
                  '중앙': round(float(g['보고하한'].median()), 2),
                  '최소': round(float(g['보고하한'].min()), 2),
                  '최대': round(float(g['보고하한'].max()), 2)})
    점 = [{'이름': r['이름'], '축': r['축'], '유효인원': round(float(r['유효인원']), 1),
          '평가행': int(r['평가행']), '보고하한': round(float(r['보고하한']), 3),
          '보정': r['보정'], 't': round(float(r['t']), 3)}
         for _, r in d.iterrows()]
    print('  {} 창 / 점 {}개 / log-log 기울기 {:.3f}'.format(창, len(점), 기울기))
    return {'점': 점, '띠': 띠,
            '적합': {'기울기': round(float(기울기), 4), '절편': round(float(절편), 4)}}


# ── 실행 ────────────────────────────────────────────────────────────────
print('1. N-Day 리텐션 (창과 무관)')
저장('nday.json', nday())

만든창 = []
for 창 in ['2일', '14일']:      # 주 분석(2일)을 앞에 — 페이지 단추도 이 차례로 나옴
    if not 쓸파일('무주입_조건', 창):
        print('{} 창 — 결과 파일이 없어 건너뜀'.format(창))
        continue
    print('{} 창 — 평가 {} / 판정선 {:.3f}'.format(
        창, 창설정[창]['평가기간'], 창설정[창]['판정선']))
    날짜별 = d1_daily(창)
    저장('d1_daily_{}.json'.format(창), 날짜별)
    # 평가 기간 평균 편차 — 본문에 「평균 +1.46%p」 로 박혀 있던 값. 창마다 다름
    _평가 = [p for p in 날짜별['점'] if p['구간'] == '평가']
    _분모 = sum(p['분모'] for p in _평가)
    평가편차 = sum((p['D1'] - p['기대']) * p['분모'] for p in _평가) / _분모 * 100
    저장('groups_{}.json'.format(창), groups(창))
    저장('curve_{}.json'.format(창), curve(창))
    # 14일 파일에는 중복 26개가 들어 있음(10/11 에 바로잡기 전에 만든 것) — 이름으로 셈
    무 = pd.read_csv(쓸파일('무주입_조건', 창), encoding='utf-8-sig').drop_duplicates('이름')
    저장('meta_{}.json'.format(창), {
        '창': 창,
        '판정선': 창설정[창]['판정선'],
        '학습기간': '기준일 3/1~3/15 (결과일 3/2~3/16)',
        '평가기간': 창설정[창]['평가기간'],
        '습관측정': '2/1~2/28 (고정)',
        '분석행': 8802984 + 창설정[창]['평가행'],
        '학습행': 8802984, '평가행': 창설정[창]['평가행'],
        '유효인원': 창설정[창]['유효인원'], '조건수': len(무),
        '평가편차': round(평가편차, 2),
        '만든날': pd.Timestamp.today().strftime('%Y-%m-%d'),
    })
    만든창.append(창)

if not 만든창:
    raise SystemExit('만든 창이 하나도 없음 — results/ 에 무주입_조건_*.csv 가 있어야 함')

# 창 이름 없는 옛 파일도 주 분석 것으로 같이 남김.
# 브라우저에 **옛 app.js 가 캐시돼 있으면** groups.json·curve.json·meta.json·
# d1_daily.json 을 찾는데, 이름만 바꿔 버리면 그 사람 화면은 통째로 죽음
# (10/11 에 실제로 그랬음). 몇십 KB 더 두는 값으로 그걸 막음
주창 = 주분석 if 주분석 in 만든창 else 만든창[0]
for 이름 in ('d1_daily', 'groups', 'curve', 'meta'):
    새것 = os.path.join(OUT, '{}_{}.json'.format(이름, 주창))
    shutil.copyfile(새것, os.path.join(OUT, '{}.json'.format(이름)))
print('  옛 이름 4개도 {} 창 것으로 남김 (캐시된 옛 app.js 대비)'.format(주창))
저장('창목록.json', {'창': 만든창,
                 '기본': 주분석 if 주분석 in 만든창 else 만든창[0],
                 '설명': {c: 창설정[c]['평가기간'] for c in 만든창}})
print(NL + '끝 — ' + OUT + '  (창 ' + ', '.join(만든창) + ')')
