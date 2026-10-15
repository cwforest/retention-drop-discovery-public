# -*- coding: utf-8 -*-
"""찾음하한_2조건_{창}.csv 의 칸을 3조건 파일(최신)에 맞춤.

왜 어긋났나
  10/12 에 `fix_dodal.py` 가 도달δ예측의 `√r` 근사를 정확식으로 고칠 때
  파일마다 다르게 처리했음 —
    쌍_조용_*.csv        : 도달δ예측 을 **덮어씀** (근사는 도달δ예측_근사 로 남김)
    찾음하한_2조건_*.csv : 도달δ예측_정확·막힘_정확 을 **덧붙임** (원래 칸은 안 건드림)
    찾음하한_3조건_*.csv : 고친 뒤에 만들어져 **처음부터 정확식**
  그래서 같은 이름인 `도달δ예측` 이 2조건에서는 근사, 3조건에서는 정확식이 됐음.
  두 파일을 나란히 놓고 비교하면 근사와 정확식을 비교하는 꼴이라 틀림.

맞추는 것 (3조건 기준)
  도달δ예측_정확 → 도달δ예측      (옛 근사값은 버림 — 쌍_조용_*.csv 와 백업에 남아 있음)
  막힘_정확      → 무엇에막히나
  예측하한        = max(보고δ예측, 정확 도달δ예측) 로 다시 계산
  비중            = 평가행 ÷ 그 창의 평가 전체 행수 (없으면 새로 넣음)
  상한·상한에서찾음 = 없으면 채움 (14일 파일에 없음)
  칸 차례도 3조건과 같게 맞춤

실험 결과(찾음하한) 자체는 **손대지 않음.** 그건 빔 서치가 잰 값이라
예측식을 고쳐도 바뀌지 않음. 바뀌는 건 「예측이 얼마나 맞았나」 뿐임.

쓰는 법 (저장소 루트에서):
  python scripts/align_cols.py          # 고침
  python scripts/align_cols.py --보기   # 무엇이 바뀌는지만 찍고 파일은 안 건드림
"""
import io
import os
import shutil
import sys

import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

RES = 'results'
백업 = os.path.join(RES, '백업_20261012')

# 창마다 다른 평가 전체 행수 — 비중의 분모임 (build_web_data.py 의 창설정과 같은 값)
평가행수 = {'2일': 1204768, '14일': 8407908}

# 3조건 파일의 차례. 조건 2개는 'C' 만 빠짐
차례 = ['A', 'B', 'C', '희석칸', '평가행', '비중', '희석r',
       '보고δ예측', '도달δ예측', '예측하한', '무엇에막히나',
       '찾음하한', '상한', '상한에서찾음', '최고겹침']


def 맞추기(창, 보기만):
    경로 = os.path.join(RES, '찾음하한_2조건_{}.csv'.format(창))
    if not os.path.exists(경로):
        print('{} — 파일 없음, 건너뜀'.format(창))
        return
    d = pd.read_csv(경로, encoding='utf-8-sig')
    바뀜 = []

    # ① 도달δ예측 — 정확식으로 갈아끼움
    if '도달δ예측_정확' in d.columns:
        d['도달δ예측'] = d['도달δ예측_정확']
        d = d.drop(columns=['도달δ예측_정확'])
        바뀜.append('도달δ예측 ← 도달δ예측_정확 (옛 근사는 버림)')

    # ② 판정 칸 이름
    if '막힘_정확' in d.columns:
        d['무엇에막히나'] = d['막힘_정확']
        d = d.drop(columns=['막힘_정확'])
        바뀜.append('무엇에막히나 ← 막힘_정확')
    elif '무엇에막히나' not in d.columns:
        d['무엇에막히나'] = np.where(d['도달δ예측'] > d['보고δ예측'],
                                '도달(빔)', '보고(판정선)')
        바뀜.append('무엇에막히나 새로 계산')

    # ③ 예측하한 — 정확식 도달로 다시
    옛예측 = d['예측하한'].to_numpy(dtype='float64').copy()
    d['예측하한'] = np.maximum(d['보고δ예측'], d['도달δ예측'])
    달라진 = ~np.isclose(옛예측, d['예측하한'].to_numpy(dtype='float64'))
    if 달라진.any():
        바뀜.append('예측하한 다시 계산 — {}개 집단이 달라짐'.format(int(달라진.sum())))
        for i in np.where(달라진)[0]:
            바뀜.append('    {:<44.44s} {:.2f} → {:.2f}'.format(
                d['A'].iloc[i] + ' × ' + d['B'].iloc[i],
                옛예측[i], d['예측하한'].iloc[i]))

    # ④ 비중
    if '비중' not in d.columns:
        d['비중'] = (d['평가행'] / 평가행수[창]).round(5)
        바뀜.append('비중 새로 넣음 (평가 전체 {:,}행 기준)'.format(평가행수[창]))

    # ⑤ 상한 — 14일 파일에 없음. 그때 쓰던 식으로 되살림
    if '상한' not in d.columns:
        d['상한'] = np.maximum(옛예측 * 1.4, 2.0).round(4)
        바뀜.append('상한 되살림 — 그때 쓰던 max(예측하한 × 1.4, 2.0). '
                   '⚠️ 옛 예측하한(근사)으로 잡은 값이라 기록용임')
    if '상한에서찾음' not in d.columns:
        d['상한에서찾음'] = d['찾음하한'].notna()
        바뀜.append('상한에서찾음 새로 넣음 (찾음하한이 비었나로 판단)')

    # ⑥ 안 쓰는 칸 버림 — 쌍_조용_*.csv 와 백업에 남아 있음
    버릴것 = [c for c in ('도달δ예측_근사', '부모이미빔안') if c in d.columns]
    if 버릴것:
        d = d.drop(columns=버릴것)
        바뀜.append('{} 버림 (쌍_조용_{}.csv 와 백업에 있음)'.format(', '.join(버릴것), 창))

    # ⑦ 차례 맞추기
    남은것 = [c for c in 차례 if c in d.columns] + [c for c in d.columns if c not in 차례]
    d = d[남은것]

    print('[{}] {}'.format(창, 경로))
    for x in 바뀜:
        print('  ' + x)
    print('  칸 {}개 → {}'.format(len(d.columns), list(d.columns)))
    if 보기만:
        print('  (--보기 라 저장 안 함)')
        return

    os.makedirs(백업, exist_ok=True)
    뒷자리 = os.path.join(백업, '칸맞추기전_찾음하한_2조건_{}.csv'.format(창))
    if not os.path.exists(뒷자리):
        shutil.copyfile(경로, 뒷자리)
        print('  원본 보관: ' + 뒷자리)
    d.to_csv(경로, index=False, encoding='utf-8-sig')
    print('  저장: ' + 경로)


def 확인():
    """두 파일의 칸이 (C 만 빼고) 같아졌는지 봄"""
    a = pd.read_csv(os.path.join(RES, '찾음하한_2조건_2일.csv'), encoding='utf-8-sig')
    b = pd.read_csv(os.path.join(RES, '찾음하한_3조건_2일.csv'), encoding='utf-8-sig')
    A = [c for c in a.columns]
    B = [c for c in b.columns if c != 'C']
    print()
    print('2조건 {}'.format(A))
    print('3조건 {}  (C 뺌)'.format(B))
    print('→ {}'.format('같음' if A == B else '아직 다름: {} / {}'.format(
        [c for c in A if c not in B], [c for c in B if c not in A])))


if __name__ == '__main__':
    보기만 = '--보기' in sys.argv[1:]
    for 창 in ('2일', '14일'):
        맞추기(창, 보기만)
        print()
    if not 보기만:
        확인()
