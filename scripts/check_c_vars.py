"""C 후보 변수 점검 — 구독 연차 · 과거 결제 빈도 · 과거 취소 이력

넣을지 말지를 정하려고 재는 것임. 모델을 다시 학습하지 않고 **집단 탐색 축**으로만
쓸 생각이므로, 보는 것은 네 가지임.

  ① 만들 수 있나   — 결측률, 좌측 절단률(데이터가 2015-01 에서 시작함)
  ② 중복 아닌가     — 이미 있는 변수와의 상관 (특히 days_since_signup)
  ③ 설명력 있나     — 5구간으로 잘랐을 때 D1 스프레드 (최대 구간 - 최소 구간)
  ④ 이상 흡수 안 하나 — 측정 시점이 기준일에 따라 움직이는지

측정 시점 규칙 (설계 문서과 같은 원칙):
  · 구독 연차는 기준일마다 계산해도 됨 — 첫 거래일이 과거에 고정돼 있고
    연차는 하루에 1씩 결정론적으로 늘어나므로 평가 기간의 이상을 흡수하지 않음
  · 과거 결제 빈도 · 취소 이력은 **2/28 까지로 고정** — 기준일까지 누적으로 세면
    평가 기간에 해지한 사람의 값이 변해서 찾아야 할 이상을 흡수함 (계획서 표 6)

실행:  python scripts/check_c_vars.py      (impok 환경)
"""

import numpy as np
import pandas as pd

DATA = 'data'
TRAIN_LAST = 14          # 학습(정상) 기간 마지막 기준일 — 3/15
EVAL_LAST = 28           # 평가 기간 마지막 기준일 — 3/29 (3/30 은 경계 효과라 뺌)
ORIGIN = '2017-03-01'    # 날짜 번호 0 이 3/1 임
FEB_LAST = -1            # 2/28 의 날짜 번호 (고정 측정 마감일)
DATA_START = -760        # 2015-01-31 — 이보다 앞이면 '데이터가 시작되는 달' 에 붙은 것임

pd.set_option('display.width', 150)


def ymd_to_offset(v):
    """YYYYMMDD 정수를 '3/1 로부터 며칠' 로 바꿈.
       날짜 종류가 수백 개뿐이라 고유값만 변환한 뒤 되돌려 붙임 (build_mart 6절과 같은 방식)"""
    u = np.unique(v)
    off = (pd.to_datetime(pd.Series(u).astype(str), format='%Y%m%d', errors='coerce')
           - pd.Timestamp(ORIGIN)).dt.days.to_numpy().astype('float64')
    return off[np.searchsorted(u, v)]


def 구간나누기(값, 학습, 구간수=5):
    """학습(정상) 기간 분포의 분위수로 경계를 고정함 — 설계 규칙임.
       결측은 0번 칸으로 따로 둠 (결측으로는 조건을 만들 수 없어 값 하나로 세워야 함)"""
    자를곳 = np.unique(np.nanquantile(값[학습], np.linspace(0, 1, 구간수 + 1)))
    이름 = []
    for i in range(len(자를곳) - 1):
        if i == 0:
            이름.append('≤{:g}'.format(자를곳[i + 1]))
        elif i == len(자를곳) - 2:
            이름.append('>{:g}'.format(자를곳[i]))
        else:
            이름.append('{:g}~{:g}'.format(자를곳[i], 자를곳[i + 1]))
    자를곳[0], 자를곳[-1] = -np.inf, np.inf
    코드 = (pd.cut(값, 자를곳).codes + 1).astype('int16')     # 결측 = 0
    return 코드, ['(결측)'] + 이름


def 스프레드표(이름, 코드, 값이름, d1, 학습, 평가):
    """구간별 D1 을 찍고 스프레드(최대-최소)를 돌려줌. 설명력이 있는 축인지 보는 자리임"""
    줄 = []
    for i, nm in enumerate(값이름):
        m = 코드 == i
        if not m.any():
            continue
        줄.append({'구간': nm,
                   '학습행': int((m & 학습).sum()),
                   '평가행': int((m & 평가).sum()),
                   '비율': m.mean(),
                   'D1': d1[m].mean()})
    표 = pd.DataFrame(줄)
    스프레드 = (표['D1'].max() - 표['D1'].min()) * 100
    print('\n[{}]  구간 {}개 / D1 스프레드 {:.2f}%p'.format(이름, len(표), 스프레드))
    print(표.assign(비율=lambda d: (d['비율'] * 100).round(2),
                    D1=lambda d: (d['D1'] * 100).round(2)).to_string(index=False))
    return 스프레드


# ── 1. 거래 데이터에서 유저별 후보값을 만듦 ──────────────────────────────
print('=' * 78)
print('1. 거래 데이터 읽기')
print('=' * 78)

uniq = pd.read_parquet(f'{DATA}/cache/active_users.parquet')['msno']
n_user = len(uniq)
print('3월 활동 유저 {:,}명'.format(n_user))

tx = pd.read_parquet(f'{DATA}/transactions_all.parquet',
                     columns=['msno', 'transaction_date', 'is_cancel'])
print('거래 {:,}건'.format(len(tx)))

tc = pd.Categorical(tx['msno'], categories=uniq).codes.astype('int32')   # -1 = 3월 활동 유저 아님
tday = ymd_to_offset(tx['transaction_date'].to_numpy())
cancel = tx['is_cancel'].to_numpy().astype('int8')
del tx

keep = tc >= 0
tc, tday, cancel = tc[keep], tday[keep].astype('int32'), cancel[keep]
print('그중 3월 활동 유저의 거래 {:,}건'.format(len(tc)))
print('거래일 범위 {} ~ {} (날짜 번호)'.format(tday.min(), tday.max()))

# ① 유저별 첫 거래일 — (유저, 거래일) 순으로 세우고 그룹의 첫 줄을 집음
#    np.minimum.at 은 2,300만 건에서 너무 느려 정렬로 구함
_o = np.lexsort((tday, tc))
_tc_s, _td_s = tc[_o], tday[_o]
_첫줄 = np.flatnonzero(np.r_[True, np.diff(_tc_s) != 0])
first_tx = np.full(n_user, np.nan, 'float32')
first_tx[_tc_s[_첫줄]] = _td_s[_첫줄]
del _o, _tc_s, _td_s, _첫줄

# ②③ 2/28 까지로 **고정** 측정 — 기준일마다 갱신하지 않음
_과거 = tday <= FEB_LAST
n_pay = np.bincount(tc[_과거 & (cancel == 0)], minlength=n_user).astype('int32')
n_cancel = np.bincount(tc[_과거 & (cancel == 1)], minlength=n_user).astype('int32')
del tc, tday, cancel

print('\n유저 단위 집계 완료')
print('  첫 거래 있는 유저 {:,}명 ({:.1%})'.format(
    np.isfinite(first_tx).sum(), np.isfinite(first_tx).mean()))
print('  2/28 까지 결제 이력 있는 유저 {:,}명 ({:.1%})'.format(
    (n_pay > 0).sum(), (n_pay > 0).mean()))
print('  2/28 까지 취소 이력 있는 유저 {:,}명 ({:.1%})'.format(
    (n_cancel > 0).sum(), (n_cancel > 0).mean()))


# ── 2. 분석 테이블에 붙임 ────────────────────────────────────────────────
print('\n' + '=' * 78)
print('2. 분석 테이블에 붙이기')
print('=' * 78)

mart = pd.read_parquet(f'{DATA}/mart.parquet',
                       columns=['u', 'day', 'd1', 'days_since_signup', 'has_tx', 'is_cancel', 'act_days'])
mart = mart[mart['day'] <= EVAL_LAST]
u = mart['u'].to_numpy()
day = mart['day'].to_numpy().astype('int32')
d1 = mart['d1'].to_numpy()
학습 = day <= TRAIN_LAST
평가 = ~학습
print('행 {:,} (학습 {:,} + 평가 {:,})'.format(len(mart), 학습.sum(), 평가.sum()))

# ① 구독 연차 = 기준일 - 첫 거래일. 첫 거래 전이면 결측 (아직 가입 전이라 연차가 없음)
tenure = day - first_tx[u]
tenure[tenure < 0] = np.nan
# 누수 점검 — 연차는 기준일까지의 정보로만 만들어졌으므로 음수가 남아 있으면 안 됨
assert np.nanmin(tenure) >= 0, '연차에 음수가 있음 — 첫 거래가 기준일 이후임'

# ②③ 고정값이라 행마다 같은 값이 붙음
pay_cnt = n_pay[u]
cancel_cnt = n_cancel[u]


# ── 3. ① 구독 연차 ───────────────────────────────────────────────────────
print('\n' + '=' * 78)
print('3. ① 구독 연차  (기준일 - 첫 거래일, 기준일마다 갱신해도 안전)')
print('=' * 78)

_결측 = ~np.isfinite(tenure)
_절단유저 = first_tx <= DATA_START
_절단행 = np.isfinite(tenure) & _절단유저[u]
print('결측(첫 거래 없음)  {:,}행 ({:.2%})  ← 진짜 무료 유저'.format(_결측.sum(), _결측.mean()))
print('좌측 절단(2015-01)  {:,}행 ({:.2%})  ← 실제 연차는 더 길 수 있음'.format(
    _절단행.sum(), _절단행.mean()))
print('has_tx=False 와 결측이 같은가:',
      np.array_equal(_결측, ~mart['has_tx'].to_numpy()))

_유한 = np.isfinite(tenure)
print('\n연차 분포 (일):')
print(pd.Series(tenure[_유한]).describe(
    percentiles=[.1, .25, .5, .75, .9]).round(1).to_string())
print('  = 연 단위로는 {:.1f}년 ~ {:.1f}년'.format(
    np.nanmin(tenure) / 365, np.nanmax(tenure) / 365))

# 중복 점검 — 가입 후 경과일과 얼마나 같은 말을 하는지
_dss = mart['days_since_signup'].to_numpy()
_둘다 = _유한 & np.isfinite(_dss)
print('\ndays_since_signup 과의 상관 (피어슨) {:.3f}'.format(
    np.corrcoef(tenure[_둘다], _dss[_둘다])[0, 1]))
print('  (10/5 점검값 0.49 와 맞는지 확인용. 0.9 를 넘으면 같은 말이라 넣을 이유가 없음)')

_c1, _n1 = 구간나누기(tenure, 학습)
s1 = 스프레드표('구독 연차', _c1, _n1, d1, 학습, 평가)

# 연 단위로 잘라 보기 — 해석하기 쉬운 경계가 더 나은지 봄
_연경계 = np.array([-np.inf, 365, 730, 1095, np.inf])
_c1y = (pd.cut(tenure, _연경계).codes + 1).astype('int16')
s1y = 스프레드표('구독 연차 (연 단위 경계)', _c1y,
                 ['(결측)', '1년 미만', '1~2년', '2~3년', '3년+'], d1, 학습, 평가)


# ── 4. ② 과거 결제 빈도 (2/28 고정) ─────────────────────────────────────
print('\n' + '=' * 78)
print('4. ② 과거 결제 빈도  (2/28 까지의 결제 건수, 고정)')
print('=' * 78)

print('0건 비율 {:.2%}   (0건 = 2/28 까지 결제 기록이 없음)'.format((pay_cnt == 0).mean()))
print(pd.Series(pay_cnt).describe(percentiles=[.25, .5, .75, .9, .99]).round(1).to_string())

_c2, _n2 = 구간나누기(pay_cnt.astype('float64'), 학습)
s2 = 스프레드표('과거 결제 건수', _c2, _n2, d1, 학습, 평가)

print('\nhas_tx 와의 교차 (결제 0건인데 거래는 있는 경우 = 취소 기록만 있는 유저):')
print(pd.crosstab(pd.Series(pay_cnt > 0, name='과거 결제 있음'),
                  pd.Series(mart['has_tx'].to_numpy(), name='has_tx')).to_string())


# ── 5. ③ 과거 취소 이력 (2/28 고정) ─────────────────────────────────────
print('\n' + '=' * 78)
print('5. ③ 과거 취소 이력  (2/28 까지의 취소 건수, 고정)')
print('=' * 78)

print('0건 비율 {:.2%}'.format((cancel_cnt == 0).mean()))
print(pd.Series(cancel_cnt).describe(percentiles=[.5, .75, .9, .99]).round(2).to_string())

_c3 = np.where(cancel_cnt == 0, 1, np.where(cancel_cnt == 1, 2, 3)).astype('int16')
s3 = 스프레드표('과거 취소 횟수', _c3, ['(안 씀)', '0회', '1회', '2회+'], d1, 학습, 평가)

print('\n현재 is_cancel 과의 교차 (지금 해지 상태인가 vs 과거에 해지한 적 있나):')
_now = mart['is_cancel'].to_numpy()
print(pd.crosstab(pd.Series(cancel_cnt > 0, name='과거 취소 있음'),
                  pd.Series(np.where(np.isnan(_now), -1, _now), name='현재 is_cancel'),
                  normalize='all').round(4).to_string())


# ── 6. 판단표 ────────────────────────────────────────────────────────────
print('\n' + '=' * 78)
print('6. 한눈에')
print('=' * 78)
요약 = pd.DataFrame([
    {'후보': '① 구독 연차 (분위 5구간)', '결측률': _결측.mean(), 'D1 스프레드(%p)': s1},
    {'후보': '① 구독 연차 (연 단위)', '결측률': _결측.mean(), 'D1 스프레드(%p)': s1y},
    {'후보': '② 과거 결제 빈도', '결측률': 0.0, 'D1 스프레드(%p)': s2},
    {'후보': '③ 과거 취소 이력', '결측률': 0.0, 'D1 스프레드(%p)': s3},
])
print(요약.assign(**{'결측률': lambda d: (d['결측률'] * 100).round(2),
                     'D1 스프레드(%p)': lambda d: d['D1 스프레드(%p)'].round(2)}).to_string(index=False))
print('\n비교 기준 — 기존 D 변수 중 가장 약한 pct_full 이 5.2%p 임 (설계 문서).')
print('이보다 낮으면 축을 늘리는 값이 크지 않음.')


# ── 7. 편차로 다시 보기 ──────────────────────────────────────────────────
# D1 스프레드는 '수준'을 재는 것인데, 집단 탐색이 보는 것은 기대 모델을 통과한 뒤의
# **편차**임. 수준 차이가 커도 모델이 이미 설명했으면 편차는 평평해서 가설이 안 나옴.
# 반대도 마찬가지임. 그래서 축으로 쓸 값이 있는지는 편차로 봐야 함.
print('\n' + '=' * 78)
print('7. 편차로 다시 보기  (탐색 축으로서의 값)')
print('=' * 78)

pred = pd.read_parquet(f'{DATA}/pred.parquet', columns=['u', 'day', 'dev'])
pred = pred[pred['day'] <= EVAL_LAST]
assert len(pred) == len(mart), '행 수가 안 맞음'
assert (pred['u'].to_numpy() == u).all(), '유저 번호 순서가 다름'
dev = pred['dev'].to_numpy().astype('float64')
del pred

_전체학습 = dev[학습].mean() * 100
_전체평가 = dev[평가].mean() * 100
print('전체 — 학습 평균 편차 {:+.4f}%p / 평가 {:+.4f}%p / 차이 {:+.4f}%p'.format(
    _전체학습, _전체평가, _전체평가 - _전체학습))
print('(차이가 0이 아닌 것은 평가 기간 전체가 기대보다 더 돌아왔기 때문임 - 전체 기준선)')


def 편차표(이름, 코드, 값이름):
    """구간별 학습·평가 평균 편차와 '전체 대비 얼마나 다르게 움직였나'를 봄.
       마지막 칸(상대)이 전체 기준선만 뺀 거친 보정후임 - 기울기는 무시한 값임"""
    줄 = []
    for i, nm in enumerate(값이름):
        m = 코드 == i
        if not m.any():
            continue
        _h, _e = (m & 학습), (m & 평가)
        if _h.sum() < 2 or _e.sum() < 2:
            continue
        a, b = dev[_h].mean() * 100, dev[_e].mean() * 100
        줄.append({'구간': nm, '평가행': int(_e.sum()),
                   '학습편차': a, '평가편차': b, '차이': b - a,
                   '상대': (b - a) - (_전체평가 - _전체학습)})
    표 = pd.DataFrame(줄)
    print('\n[{}]  학습편차 퍼짐 {:.2f}%p / 상대 퍼짐 {:.2f}%p'.format(
        이름, 표['학습편차'].max() - 표['학습편차'].min(),
        표['상대'].max() - 표['상대'].min()))
    print(표.round(3).to_string(index=False))


편차표('① 구독 연차', _c1, _n1)
편차표('① 구독 연차 (연 단위)', _c1y, ['(결측)', '1년 미만', '1~2년', '2~3년', '3년+'])
편차표('② 과거 결제 건수', _c2, _n2)
편차표('③ 과거 취소 횟수', _c3, ['(안 씀)', '0회', '1회', '2회+'])

# 비교용 - 이미 쓰고 있는 축들. 이 정도는 돼야 축을 늘릴 값이 있음
_act = mart['act_days'].to_numpy().astype('float64')
_cA = (pd.cut(_act, [-1, 0, 3, 10, 20, 28]).codes + 1).astype('int16')
편차표('(비교) act_days', _cA,
       ['없음', '0 (미측정)', '1-3일', '4-10일', '11-20일', '21-28일'])
편차표('(비교) has_tx', mart['has_tx'].to_numpy().astype('int16'), ['거래 없음', '거래 있음'])
