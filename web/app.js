// 페이지는 계산을 하지 않음. scripts/build_web_data.py 가 만들어 둔 JSON 을 읽어 그리기만 함.
'use strict';

const DATA = 'web/data/';
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

// 창을 바꾸면 같은 캔버스에 다시 그리게 됨. Chart.js 는 옛 차트를 치우지 않으면
// 두 개가 겹쳐 남아 마우스를 올릴 때 엉뚱한 값이 뜨므로 여기 모아 두고 버림
const 그린것 = {};
function 캔버스(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  if (그린것[id]) { 그린것[id].destroy(); delete 그린것[id]; }
  return el;
}
function 기억(id, 차트) { 그린것[id] = 차트; return 차트; }

async function 읽기(이름) {
  try {
    const r = await fetch(DATA + 이름, { cache: 'no-store' });
    if (!r.ok) return null;
    return await r.json();
  } catch (e) {
    return null;
  }
}

// Chart.js 공통 설정 — 글자색·격자색을 CSS 변수에서 가져옴
function 기본옵션() {
  const dim = css('--dim'), line = css('--line');
  Chart.defaults.color = dim;
  Chart.defaults.borderColor = line;
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.font.size = 11;
}

// ── 그림 A. N-Day 리텐션 ─────────────────────────────────────────────
function 그림_nday(d) {
  const el = 캔버스('chart-nday');
  if (!d || !el) return;
  document.getElementById('nday-users').textContent = d['유저수'].toLocaleString();
  기억('chart-nday', new Chart(el, {
    type: 'line',
    data: {
      labels: d['점'].map(p => 'D' + p.day),
      datasets: [{
        data: d['점'].map(p => +(p['리텐션'] * 100).toFixed(2)),
        borderColor: css('--accent'),
        backgroundColor: css('--accent') + '22',
        borderWidth: 2, pointRadius: 2.5, pointHoverRadius: 5, fill: true, tension: .25
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => {
              const p = d['점'][c.dataIndex];
              return `${c.parsed.y}%  (분모 ${p['분모'].toLocaleString()}명)`;
            }
          }
        }
      },
      scales: {
        y: { min: 0, max: 100, ticks: { callback: v => v + '%' } },
        x: { grid: { display: false } }
      }
    }
  }));
}

// ── 그림 B. 기준일별 D1 ──────────────────────────────────────────────
// 학습/평가 구간을 배경 띠로 칠하는 작은 플러그인
const 띠플러그인 = {
  id: '띠',
  beforeDatasetsDraw(chart, args, opts) {
    const { ctx, chartArea: a, scales: { x } } = chart;
    if (!opts || !opts.구간) return;
    ctx.save();
    const 칸 = x.width / Math.max(1, x.max - x.min);   // 한 칸의 픽셀 폭
    opts.구간.forEach(z => {
      const x1 = x.getPixelForValue(z.시작) - 칸 / 2;
      const x2 = x.getPixelForValue(z.끝) + 칸 / 2;
      ctx.fillStyle = z.색;
      ctx.fillRect(x1, a.top, x2 - x1, a.bottom - a.top);
      ctx.fillStyle = css('--dim');
      ctx.font = '600 10px ' + Chart.defaults.font.family;
      ctx.fillText(z.이름, x1 + 6, a.top + 13);
    });
    ctx.restore();
  }
};

function 그림_d1(d) {
  const el = 캔버스('chart-d1');
  if (!d || !el) return;
  const 점 = d['점'];
  const 학습 = 점.filter(p => p['구간'] === '학습');
  const 평가 = 점.filter(p => p['구간'] === '평가');
  기억('chart-d1', new Chart(el, {
    type: 'line',
    plugins: [띠플러그인],
    data: {
      labels: 점.map(p => p['날짜']),
      datasets: [{
        label: '실제 재방문율',
        data: 점.map(p => +(p['D1'] * 100).toFixed(2)),
        borderColor: css('--accent'),
        borderWidth: 2.2, pointRadius: 2, pointHoverRadius: 5, tension: .2,
        segment: {
          borderColor: (c) => 점[c.p1DataIndex]['구간'] === '제외'
            ? css('--faint') : css('--accent')
        }
      }, {
        // 기대 모델이 낸 확률. 두 선의 틈이 곧 '편차' 임
        label: '기대 모델 예측',
        data: 점.map(p => +(p['기대'] * 100).toFixed(2)),
        borderColor: css('--sky-2'),
        borderWidth: 1.8, borderDash: [5, 4],
        pointRadius: 0, pointHoverRadius: 4, tension: .2
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          display: true, position: 'bottom',
          labels: { boxWidth: 22, boxHeight: 2, padding: 14, font: { size: 11 } }
        },
        띠: {
          // 카테고리 축이라 라벨이 아니라 '몇 번째 칸인지'로 넘김
          구간: [
            { 시작: 점.indexOf(학습[0]), 끝: 점.indexOf(학습[학습.length - 1]),
              색: css('--line') + '77', 이름: '학습(정상)' },
            { 시작: 점.indexOf(평가[0]), 끝: 점.indexOf(평가[평가.length - 1]),
              색: css('--warm') + '18', 이름: '평가' }
          ]
        },
        tooltip: {
          callbacks: {
            title: (cs) => {
              const p = 점[cs[0].dataIndex];
              return `${p['날짜']} (${p['요일']}) · ${p['구간']}`;
            },
            label: (c) => `${c.dataset.label} ${c.parsed.y}%`,
            footer: (cs) => {
              const p = 점[cs[0].dataIndex];
              const 편차 = (p['D1'] - p['기대']) * 100;
              return `편차 ${편차 >= 0 ? '+' : ''}${편차.toFixed(2)}%p · 분모 ${p['분모'].toLocaleString()}`;
            }
          }
        }
      },
      scales: {
        y: { min: 72, max: 82, ticks: { callback: v => v + '%' } },
        x: { grid: { display: false }, ticks: { maxTicksLimit: 10 } }
      }
    }
  }));
}

// ── δ 슬라이더 ───────────────────────────────────────────────────────
// 조건 1개 묶음과 조건 2개 묶음을 각각 그림. 둘은 슬라이더도 따로 씀.
const MAXδ = 20;      // 기본 눈금. 묶음마다 다를 수 있어 상자에 적어 두고 꺼내 씀
// ── 하한 막대 (조건 2개·3개) ─ fix_page_find_charts.py 가 넣음 ─
// 단추로 고른 값. 창을 바꿔도 유지되도록 바깥에 둠
const 하한칸 = { '조건 2개': '찾음δ', '조건 3개': '찾음δ' };
let 마지막gr = null;

function 단추묶기() {
  document.querySelectorAll('.wintabs[data-find]').forEach(묶음 => {
    const 종류 = '조건 ' + 묶음.dataset.find + '개';
    묶음.querySelectorAll('button').forEach(b => {
      b.addEventListener('click', () => {
        하한칸[종류] = b.dataset.kind;
        묶음.querySelectorAll('button').forEach(x => x.classList.remove('on'));
        b.classList.add('on');
        그림_찾음(마지막gr, 종류,
          'chart-find' + 묶음.dataset.find, 'find' + 묶음.dataset.find + '-wrap');
      });
    });
  });
}

// 세 조건을 다 적으면 80자라 칸에 안 들어가고, 글자 수로 자르면 첫 조건이
// 중간에서 끊겨 읽히지 않음 ('days_since_last ≤0 AN…').
// 그래서 첫 조건만 남기고 나머지는 「+2」로 셈 — 전체 이름은 마우스를 올리면 뜸
function 이름줄임(s, 최대) {
  const 쪽 = String(s).split(' AND ');
  const 첫 = 쪽[0].trim().replace(/\d+\.\d{3,}/g, (m) => (+m).toFixed(2));
  const 짧 = 첫.length <= 최대 ? 첫 : 첫.slice(0, 최대 - 1) + '…';
  return 쪽.length > 1 ? 짧 + '  +' + (쪽.length - 1) : 짧;
}

function 그림_찾음(gr, 종류, 캔버스id, 상자id) {
  const el = 캔버스(캔버스id);
  if (!el) return;
  const 칸 = 하한칸[종류] || '찾음δ';
  const 칸이름 = 칸 === '찾음δ' ? '찾음 하한' : '보고 하한';
  const 전부 = (gr || []).filter(g => g['종류'] === 종류);
  const 목록 = 전부.filter(g => g[칸] != null).sort((a, b) => a[칸] - b[칸]);
  const 상자 = document.getElementById(상자id);
  if (!목록.length) { if (상자) 상자.classList.add('hidden'); return; }
  if (상자) 상자.classList.remove('hidden');

  const v = 목록.map(g => g[칸]);
  const 정렬 = [...v].sort((a, b) => a - b);
  const 중앙 = 정렬.length % 2
    ? 정렬[(정렬.length - 1) / 2]
    : (정렬[정렬.length / 2 - 1] + 정렬[정렬.length / 2]) / 2;
  const 꼬리 = 상자id.replace('-wrap', '');
  const 적기 = (끝, t) => {
    const e = document.getElementById(꼬리 + '-' + 끝); if (e) e.textContent = t;
  };
  // 찾음δ 는 끝까지 못 찾은 집단이 빠지므로 그 수를 드러냄 (14일 조건 3개는 13개 중 11개)
  적기('n', 목록.length === 전부.length
    ? String(전부.length) : 전부.length + '개 중 ' + 목록.length);
  적기('mid', 중앙.toFixed(2));
  적기('ratio', (정렬[정렬.length - 1] / 정렬[0]).toFixed(0));
  적기('metric', 칸이름);

  // 막대 끝에 값, 그리고 중앙값 점선. Chart.js 기본에는 없어 직접 그림
  const 꾸밈 = {
    id: '하한꾸밈',
    afterDatasetsDraw(chart) {
      const { ctx, chartArea: a, scales: { x } } = chart;
      ctx.save();
      ctx.font = '700 11px ' + Chart.defaults.font.family;
      ctx.textBaseline = 'middle';
      ctx.fillStyle = css('--navy');
      chart.getDatasetMeta(0).data.forEach((막대, i) => {
        ctx.fillText(v[i].toFixed(2), 막대.x + 7, 막대.y);
      });
      const px = x.getPixelForValue(중앙);
      ctx.setLineDash([4, 4]);
      ctx.lineWidth = 1.4;
      ctx.strokeStyle = css('--dim');
      ctx.beginPath(); ctx.moveTo(px, a.top); ctx.lineTo(px, a.bottom); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = css('--dim');
      ctx.fillText('중앙 ' + 중앙.toFixed(2) + '%p', px + 7, a.top + 7);
      ctx.restore();
    }
  };

  기억(캔버스id, new Chart(el, {
    type: 'bar',
    plugins: [꾸밈],
    data: {
      labels: 목록.map(g => 이름줄임(g['이름'], 종류 === '조건 2개' ? 24 : 19)),
      datasets: [{
        data: v, backgroundColor: css('--accent'), borderWidth: 0,
        barPercentage: 0.72, categoryPercentage: 0.86
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      layout: { padding: { right: 36, top: 6 } },   // 막대 끝 값이 잘리지 않게
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            // 잘린 이름 때문에 어느 집단인지 헷갈리므로 전체 이름을 띄움
            title: (it) => 목록[it[0].dataIndex]['이름'],
            label: (it) => 칸이름 + ' ' + it.parsed.x.toFixed(2) + '%p'
          }
        }
      },
      scales: {
        x: {
          type: 'logarithmic',
          title: { display: true, text: 칸이름 + ' (%p) — 작을수록 작은 하락까지 잡아냄' },
          // 14일 창은 38.61%p 까지 올라가므로 40 눈금도 있어야 함
          // 로그 축은 기본으로 눈금 글자가 세로로 서 버려서 각도를 0 으로 고정함
          ticks: { maxRotation: 0, minRotation: 0, autoSkip: false,
                   callback: (v) => ([0.5, 1, 2, 5, 10, 20, 40].includes(v) ? String(v) : '') }
        },
        y: { ticks: { autoSkip: false, font: { size: 10.5 } }, grid: { display: false },
             border: { display: false } }
      }
    }
  }));
}
// ── 하한 막대 끝 ────────────────────────────────────────────

// 조건 3개는 찾음 하한이 34%p 까지 올라가 20 으로는 막대가 잘림.
// 묶음 상자(.grow)의 data-max 에 적어 두고, 줄·끌기·키보드가 모두 거기서 읽음
const 칸최대 = (el) => {
  const 상자 = el.classList && el.classList.contains('grow') ? el : el.closest('.grow');
  return (상자 && +상자.dataset.max) || MAXδ;
};

function 묶음그리기(상자, 목록, 최대) {
  상자.className = 'grow';
  상자.dataset.max = 최대;
  상자.innerHTML = 목록.map((g, i) => {
    const 찾음 = g['찾음δ'], 보고 = g['보고δ'];
    const w = (v) => Math.max(0, Math.min(100, (v / 최대) * 100));
    const 세그 = [];
    // 끝까지 못 찾은 집단은 아무것도 안 칠함.
    // 보고δ 는 '그 집단의 t 가 판정선에 닿는 δ' 라서 못 찾아도 계산은 되는데,
    // 여기서 '보고 가능' 은 **찾은 뒤에 유의한 것**을 뜻하므로 띠를 그리면 거짓말이 됨
    // (10/12 에 못 찾은 집단 둘이 남색 띠를 길게 달고 있었음)
    // 보고는 **찾은 뒤에야** 뜻이 있으므로 찾음보다 앞설 수 없음. 그래서 둘 중 큰 쪽이 경계임.
    // 이걸 안 하면 찾음 > 보고 인 집단에서 띠 너비가 음수가 돼 막대가 깨짐
    // (10/12 — 9-8 로 찾음이 12.81%p 가 된 집단에서 −54% 가 나왔음. 조건 2개 15개 중 5개가 찾음 > 보고임)
    const 경계 = 찾음 != null ? Math.max(찾음, 보고 ?? 최대) : null;
    if (찾음 != null) {
      세그.push(`<div class="seg-found" style="width:${w(경계) - w(찾음)}%;margin-left:${w(찾음)}%"></div>`);
      if (보고 != null) 세그.push(`<div class="seg-report" style="width:${100 - w(경계)}%"></div>`);
    }
    const 크기 = g['평가행'] ? `평가 ${g['평가행'].toLocaleString()}행` : '';
    const r = g['희석r'] != null ? ` · 희석 ${g['희석r']}` : '';
    const 계산 = g['종류'] === '조건 1개' ? '' : '(계산)';
    // 도달(빔) 관문에 막힌 집단 — 조건 3개에서 처음 나옴. 왜 하한이 큰지가 여기 있음
    const 관문 = g['막힘'] === '도달(빔)'
      // 「도달」 한 글자면 '도달 못 함' 으로 읽힘. 실제로는 **그 δ 를 넘으면 열리는 문턱**임
      ? `<span class="tag-gate" title="부모가 상위 20칸에 들어야 2단계로 뻗음 — 이 δ 를 넘으면 보이기 시작함">도달이 문턱</span>` : '';
    return `<div class="row" data-i="${i}">
      <div class="row-head">
        <span class="gname">${g['이름']}${관문}</span>
        <span class="gsize">${크기}${r}</span>
      </div>
      <div class="track" tabindex="0" role="slider"
           aria-label="${g['이름']} 에 심을 하락 폭"
           aria-valuemin="0" aria-valuemax="${최대}" aria-valuenow="0">
        ${세그.join('')}<div class="marker" style="left:0%"></div></div>
      <div class="row-head">
        <span class="status">—</span>
        <span class="gnums">${찾음 != null
          ? `찾음 ${찾음}%p · 보고 ${보고 != null ? 보고 + '%p' : '—'}${계산}`
            + (g['도달δ'] != null ? ` · 도달 ${g['도달δ']}%p${계산}` : '')
            // 찾음이 보고보다 뒤면 「유의한가」가 아니라 다른 것이 병목임.
            // 도달(빔)에 막힌 집단은 원인이 순위 경쟁이 아니라 **부모가 빔에 못 드는 것**이라
            // 둘을 구분해 적음 (조건 3개 15개 중 6개가 도달 쪽임)
            + (보고 != null && 찾음 > 보고
                ? (g['막힘'] === '도달(빔)' ? ' · 도달이 병목' : ' · 순위가 병목') : '')
          // 상한이 100%p 를 넘으면 애초에 심을 수가 없음(뒤집을 행이 그만큼 없음).
          // 그 숫자를 그대로 보이면 「105%p 까지 해봤다」로 읽히므로 예측값으로 바꿔 적음
          : ((g['상한'] ?? 0) > 100 && g['도달δ'] != null
              ? `도달 ${g['도달δ']}%p${계산} — 심을 수 있는 한계를 넘어 못 찾음`
              : `상한 ${(g['상한'] ?? 최대)}%p 까지 심어도 못 찾음`)}</span>
      </div>
    </div>`;
  }).join('');
}

// 막대 한 줄을 그 줄의 δ 로 다시 그림. 개별 이면 위 슬라이더와 다른 값을 쓰는 중임
function 행갱신(row, g, δ, 개별) {
  const track = row.querySelector('.track');
  const 최대 = 칸최대(row);
  track.querySelector('.marker').style.left = Math.min(100, (δ / 최대) * 100) + '%';
  const s = row.querySelector('.status');
  let 글, 반;
  if (g['찾음δ'] == null || δ < g['찾음δ']) { 글 = '못 찾음'; 반 = 's-none'; }
  else if (g['보고δ'] == null || δ < g['보고δ']) { 글 = '찾았지만 보고 불가'; 반 = 's-found'; }
  else { 글 = '보고 가능'; 반 = 's-report'; }
  // 측정한 δ 근처에 서 있으면 그 판의 실측값을 같이 보여줌.
  // 전에는 `=== δ` 로 찾았는데 측정 δ 에 0.6·0.9·1.2 처럼 0.5 눈금에 없는 값이 있어
  // 절반은 아예 뜰 수 없었음 (10/12). 가장 가까운 것을 집고 실측 δ 를 같이 적음
  const 측 = (g['측정'] || []).filter(m => Math.abs(m['δ'] - δ) < 0.3)
    .sort((a, b) => Math.abs(a['δ'] - δ) - Math.abs(b['δ'] - δ))[0];
  if (측) {
    const 딴값 = Math.abs(측['δ'] - δ) > 0.01 ? `실측 δ ${측['δ']}%p — ` : '';
    글 += `  ·  ${딴값}Hit@3 ${측['Hit3'].toFixed(2)} · 겹침 ${측['겹침'].toFixed(2)} · t ${측['정답t'].toFixed(2)}`;
  }
  s.textContent = (개별 ? `δ ${δ.toFixed(1)}%p · ` : '') + 글;
  s.className = 'status ' + 반;
  row.classList.toggle('own', !!개별);
  track.setAttribute('aria-valuenow', δ);
  track.setAttribute('aria-valuetext', `${δ.toFixed(1)}%p — ${글}`);
}

// 기준δ = 위 슬라이더 값. 개별[i] 이 null 이 아니면 그 줄은 자기 값을 씀
function 묶음갱신(상자, 목록, 기준δ, 출력, 개별) {
  출력.textContent = 기준δ.toFixed(1);
  상자.querySelectorAll('.row').forEach(row => {
    const i = +row.dataset.i;
    const 내값 = 개별[i];
    행갱신(row, 목록[i], 내값 == null ? 기준δ : 내값, 내값 != null);
  });
}

// 막대를 직접 끌기 — 그 줄만 움직임 (위 슬라이더는 전부 한꺼번에 움직임)
function 끌기붙이기(상자, 목록, 개별, 슬, 다시) {
  const 최대 = 칸최대(상자);
  // 0.5 눈금에 맞추되, 실측한 δ 가 0.3 안에 있으면 **거기에 딱 붙임**.
  // 실측값이 있는 자리에 정확히 설 수 있어야 Hit@3·겹침이 보이기 때문임
  const 맞추기 = (g, v) => {
    const 눈금 = Math.round(Math.max(0, Math.min(최대, v)) / 0.5) * 0.5;
    const 측 = (g['측정'] || []).filter(m => Math.abs(m['δ'] - 눈금) < 0.3)
      .sort((a, b) => Math.abs(a['δ'] - 눈금) - Math.abs(b['δ'] - 눈금))[0];
    return 측 ? 측['δ'] : 눈금;
  };
  const 자리값 = (track, g, clientX) => {
    const r = track.getBoundingClientRect();
    return 맞추기(g, r.width ? ((clientX - r.left) / r.width) * 최대 : 0);
  };

  상자.addEventListener('pointerdown', (e) => {
    const track = e.target.closest('.track');
    if (!track) return;
    const i = +track.closest('.row').dataset.i;
    e.preventDefault();                       // 글자가 선택되는 것을 막음
    track.focus();
    track.setPointerCapture(e.pointerId);     // 막대 밖으로 나가도 계속 따라옴
    const 옮김 = (ev) => { 개별[i] = 자리값(track, 목록[i], ev.clientX); 다시(); };
    const 끝 = () => {
      track.removeEventListener('pointermove', 옮김);
      track.removeEventListener('pointerup', 끝);
      track.removeEventListener('pointercancel', 끝);
    };
    track.addEventListener('pointermove', 옮김);
    track.addEventListener('pointerup', 끝);
    track.addEventListener('pointercancel', 끝);
    옮김(e);
  });

  // 키보드 — 탭으로 막대에 들어와 좌우 화살표. Esc 면 위 슬라이더로 되돌림
  상자.addEventListener('keydown', (e) => {
    const track = e.target.closest('.track');
    if (!track) return;
    const i = +track.closest('.row').dataset.i;
    const 지금 = 개별[i] == null ? +슬.value : 개별[i];
    let v;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') v = 지금 - 0.5;
    else if (e.key === 'ArrowRight' || e.key === 'ArrowUp') v = 지금 + 0.5;
    else if (e.key === 'Home') v = 0;
    else if (e.key === 'End') v = 최대;
    else if (e.key === 'Escape') { 개별[i] = null; 다시(); e.preventDefault(); return; }
    else return;
    e.preventDefault();
    개별[i] = Math.round(Math.max(0, Math.min(최대, v)) / 0.5) * 0.5;
    다시();
  });
}

function 묶음붙이기(상자id, 슬라이더id, 출력id, 목록) {
  // 창을 바꿀 때마다 addEventListener 가 쌓이면 한 번 끌 때 여러 번 그려짐.
  // 노드를 복제해 바꿔치면 옛 리스너가 통째로 떨어짐 (상자도 끌기 리스너를 달므로 같이 함)
  const 옛상 = document.getElementById(상자id);
  if (옛상) 옛상.replaceWith(옛상.cloneNode(false));
  const 상자 = document.getElementById(상자id);
  const 옛슬 = document.getElementById(슬라이더id);
  옛슬.replaceWith(옛슬.cloneNode(true));
  const 슬 = document.getElementById(슬라이더id);
  const 출력 = document.getElementById(출력id);
  if (!상자 || !슬 || !목록.length) return;

  const 개별 = new Array(목록.length).fill(null);   // null = 위 슬라이더를 따름
  const 최대 = +슬.max || MAXδ;                     // 눈금은 HTML 의 슬라이더가 정함
  묶음그리기(상자, 목록, 최대);
  const 다시 = () => 묶음갱신(상자, 목록, +슬.value, 출력, 개별);
  // 위 슬라이더는 **일괄** — 따로 움직여 둔 줄도 전부 같은 값으로 되돌림
  슬.addEventListener('input', () => { 개별.fill(null); 다시(); });
  끌기붙이기(상자, 목록, 개별, 슬, 다시);
  다시();
}

// ── 하한 곡선 ────────────────────────────────────────────────────────
function 그림_curve(d) {
  if (!d) return;
  document.getElementById('curve-wrap').classList.remove('hidden');
  document.getElementById('curve-n').textContent = d['점'].length.toLocaleString();
  document.getElementById('curve-slope').textContent = d['적합']['기울기'].toFixed(3);

  const 표 = document.getElementById('band-table');
  // 구간은 '평가 행' 으로 나눔 (산점도의 가로축인 유효 인원과는 다른 값임)
  표.innerHTML = '<tr><th>평가 행</th><th>집단</th><th>하한 중앙</th><th>최소~최대</th></tr>' +
    d['띠'].map(b => `<tr><td>${b['구간']}</td><td>${b['개수']}</td>
      <td class="num">${b['중앙']}%p</td><td class="num">${b['최소']}~${b['최대']}</td></tr>`).join('');

  기억('chart-curve', new Chart(캔버스('chart-curve'), {
    type: 'scatter',
    data: {
      datasets: [{
        data: d['점'].map(p => ({ x: p['유효인원'], y: p['보고하한'], 이름: p['이름'], 축: p['축'] })),
        pointRadius: 2.5, pointHoverRadius: 6,
        backgroundColor: css('--accent') + '99'
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => [c.raw['이름'],
              `유효 인원 ${Math.round(c.parsed.x).toLocaleString()}명`,
              `보고 하한 ${c.parsed.y}%p`]
          }
        }
      },
      scales: {
        x: { type: 'logarithmic', title: { display: true, text: '유효 인원 (명)' } },
        y: { type: 'logarithmic', title: { display: true, text: '보고 하한 (%p)' } }
      }
    }
  }));
}

// 4)결과 의 본문 숫자 — 창을 바꾸면 글과 숫자가 어긋나므로 데이터에서 채움.
// 조건 1개 집단 중 가장 작은 것과 가장 큰 것을 예로 씀
function 결과문구(gr, mt) {
  const 쓰기 = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  const 날 = { '2일': '이틀', '14일': '2주' };
  쓰기('win-days', 날[mt['창']] || mt['창']);
  쓰기('win-range', mt['평가기간']);

  // 목록에서 조건 1개를 뺐으므로 인용구도 조건 2개로. 조건 2개는 유효 인원을
  // 재지 않아 평가 행으로 크기를 말함. 못 찾은 집단은 보여 줄 숫자가 없어 뺌
  const 하나 = (gr || []).filter(g => g['종류'] === '조건 2개'
    && g['평가행'] != null && g['찾음δ'] != null && g['보고δ'] != null);
  if (!하나.length) return;
  // 앞 예시는 **찾음과 보고의 간격이 가장 큰 집단** — 인용구가 하려는 말이 그것임.
  // 크기로 고르면 조건 2개에서는 찾음 > 보고 인 집단이 걸려 문장이 거꾸로 됨
  // (10/14 — 「12.5%p면 집어내지만 보고하려면 11.66%p」가 나왔음)
  const 간격 = (g) => g['보고δ'] - g['찾음δ'];
  const 작 = [...하나].sort((a, b) => 간격(b) - 간격(a))[0];
  // 뒤 예시는 가장 큰 집단 — 거기서는 둘이 붙거나 뒤집힘
  const 큰 = [...하나].sort((a, b) => a['평가행'] - b['평가행']).pop();
  if (간격(작) <= 0) return;      // 간격이 하나도 안 벌어지면 이 인용구는 할 말이 없음
  const pct = (v) => v == null ? '—' : v + '%p';

  쓰기('pull-a', 작['찾음δ'] ?? '—');
  쓰기('pull-b', 작['보고δ'] ?? '—');
  쓰기('pull-a2', pct(작['찾음δ']));
  쓰기('pull-b2', pct(작['보고δ']));
  쓰기('pull-small-name', 작['이름']);
  쓰기('pull-small', 작['평가행'].toLocaleString());

  // 큰 집단은 창에 따라 이야기가 달라짐 — 14일에서는 보고가 한참 뒤에 오지만
  // 2일에서는 둘이 붙어 버림(판정선만 느슨해지고 순위 경쟁은 그대로이기 때문).
  // 글을 고정해 두면 숫자와 어긋나므로 문장째 갈아끼움
  const 꼬리 = document.getElementById('pull-tail');
  if (꼬리) {
    const 인원 = 큰['평가행'].toLocaleString();
    const 이름 = `<code>${큰['이름']}</code> 평가 ${인원}행짜리 집단`;
    const ㄱ = 큰['찾음δ'], ㄴ = 큰['보고δ'];
    꼬리.innerHTML = (ㄱ != null && ㄴ != null && ㄴ <= ㄱ * 1.05)
      ? `${이름}은 <strong>${pct(ㄱ)}</strong>과 <strong>${pct(ㄴ)}</strong>로
         둘이 거의 겹칩니다 — 집단이 크면 유의성은 더 이상 병목이 아닙니다.`
      : `${이름}은 <strong>${pct(ㄱ)} → ${pct(ㄴ)}</strong>.`;
  }

  // 도달(빔) 관문 — 조건 수마다 몇 개가 걸렸나. 창을 바꾸면 같이 바뀜
  const 센다 = (종류) => {
    const 목록 = (gr || []).filter(g => g['종류'] === 종류);
    const 막힘 = 목록.filter(g => g['막힘'] === '도달(빔)');
    return { 전체: 목록.length, 막힘: 막힘.length, 것들: 막힘 };
  };
  const g2 = 센다('조건 2개'), g3 = 센다('조건 3개');
  쓰기('gate2', `${g2.전체}개 중 ${g2.막힘}개`);
  쓰기('gate3', `${g3.전체}개 중 ${g3.막힘}개`);

  // 도달에 막힌 집단이 「보고만 보면」 몇 배를 더 떨어뜨려야 하나
  const 배 = g3.것들.filter(x => x['보고δ'] > 0 && x['도달δ'] != null)
    .map(x => x['도달δ'] / x['보고δ']).sort((p, q) => p - q);
  쓰기('gate-x', 배.length
    ? (배[0].toFixed(1) + '~' + 배[배.length - 1].toFixed(1) + '배') : '여러 배');

  // 예측한 문턱 바로 위에서 켜진 집단들 — 실제로 맞았다는 증거
  const 맞은것 = g3.것들.filter(x => x['찾음δ'] != null && x['도달δ'] != null
    && x['찾음δ'] >= x['도달δ'] && x['찾음δ'] <= x['도달δ'] * 1.25);
  const 보기칸 = document.getElementById('gate-ex');
  if (보기칸) {
    보기칸.innerHTML = 맞은것.length >= 2
      ? `실제로 ${맞은것.length}개 집단이 <strong>예측한 문턱 바로 위에서</strong> 켜졌습니다 `
        + `(앞 4개만 적으면 ` + 맞은것.slice(0, 4)
            .map(x => `${x['도달δ']}→${x['찾음δ']}`).join(', ') + ').'
      : '';
  }

  쓰기('ex1-name', 작['이름']);
  // 판 수는 측정 기록에서 — δ 단계 수 × 단계마다 돌린 횟수
  const 측 = 작['측정'] || [];
  const 판 = 측.reduce((a, r) => a + (r['판수'] || 0), 0);
  쓰기('ex1-runs', 측.length && 판
    ? `δ ${측.length}단계 × ${Math.round(판 / 측.length)}회 = 집단당 ${판}판`
    : '주입 실험');
}

// ── 돌려보기 순위표 ──────────────────────────────────────────────────
// 브라우저에서 빔 서치를 돌릴 수 없어 scripts/build_demo_data.py 가 미리 돌려 둔
// 결과를 읽기만 함. 상황(하락 없음 / 하락 심음)을 눌러 바꿈
function 그림_demo(d) {
  const 묶음 = document.getElementById('demo-tabs');
  const 몸 = document.getElementById('demo-rows');
  const 설명 = document.getElementById('demo-desc');
  if (!묶음 || !몸 || !d || !d['시나리오'] || !d['시나리오'].length) {
    const 절 = document.getElementById('try');
    if (절) 절.classList.add('hidden');      // 데이터가 없으면 절째로 숨김
    return;
  }
  const 판정선 = d['판정선'];
  const 선 = document.getElementById('demo-line');
  if (선) 선.textContent = 't = ' + 판정선.toFixed(2);

  const 그리기 = (n) => {
    const sc = d['시나리오'][n];
    for (const b of 묶음.querySelectorAll('button')) {
      const 고름 = +b.dataset.i === n;
      b.classList.toggle('on', 고름);
      b.setAttribute('aria-selected', 고름 ? 'true' : 'false');
    }
    설명.innerHTML = sc['설명'];
    몸.innerHTML = sc['순위'].map(r => {
      // 판정선보다 아래면 「우연이라 보기 어렵다」 — 진하게
      const 셈 = r['t'] <= 판정선 ? ' class="hit"' : '';
      const 표 = r['심은것'] ? '<span class="mine">심은 집단</span>' : '';
      return `<tr${셈}>
        <td class="r num">${r['순위']}</td>
        <td class="g">${r['가설']}${표}</td>
        <td class="r num">${Math.round(r['유효인원']).toLocaleString()}</td>
        <td class="r num">${r['보정후'].toFixed(2)}%p</td>
        <td class="r num">${r['t'].toFixed(2)}</td>
      </tr>`;
    }).join('');
  };

  묶음.innerHTML = d['시나리오'].map((sc, i) =>
    `<button type="button" role="tab" data-i="${i}" aria-selected="false">${sc['이름']}</button>`
  ).join('');
  묶음.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (b) 그리기(+b.dataset.i);
  });
  그리기(0);
}

// ── 시작 ─────────────────────────────────────────────────────────────
// 평가 창을 두 개(2일·14일) 만들어 두고 단추로 갈아끼움. 같은 데이터·같은 모델인데
// **평가 기간 길이만 다름** — 그래서 하한이 얼마나 달라지는지가 그대로 보임.
let 지금창 = null;

async function 창그리기(창) {
  if (창 === 지금창) return;
  지금창 = 창;

  for (const b of document.querySelectorAll('#window-tabs button')) {
    const 고름 = b.dataset.창 === 창;
    b.classList.toggle('on', 고름);
    b.setAttribute('aria-selected', 고름 ? 'true' : 'false');
  }

  const [d1, gr, cv, mt] = await Promise.all(
    ['d1_daily', 'groups', 'curve', 'meta'].map(n => 읽기(`${n}_${창}.json`)));

  if (mt) {
    document.getElementById('meta-line').textContent =
      `학습 ${mt['학습기간']} · 평가 ${mt['평가기간']} · 분석 행 ${mt['분석행'].toLocaleString()}`;
    document.getElementById('meta-bar').textContent = mt['판정선'].toFixed(2);
    document.getElementById('built').textContent = `마지막 갱신 ${mt['만든날']}`;
    for (const el of document.querySelectorAll('[data-meta]')) {
      const v = mt[el.dataset.meta];
      if (v == null) continue;
      if (typeof v !== 'number') { el.textContent = v; continue; }
      // 큰 수는 '1,000만' 꼴로 — 머리말 숫자가 열두 자리로 늘어지면 읽히지 않음
      el.textContent = el.dataset.fmt === '만'
        ? Math.round(v / 10000).toLocaleString() + '만'
        // 편차처럼 부호가 뜻을 갖는 값은 + 를 붙여 씀
        : el.dataset.fmt === '부호'
          ? (v >= 0 ? '+' : '') + v.toFixed(2)
          : v.toLocaleString();
    }
  }
  그림_d1(d1);
  if (mt) 결과문구(gr, mt);
  if (gr && gr.length) {
    묶음붙이기('groups2', 'delta2', 'delta-out2', gr.filter(g => g['종류'] === '조건 2개'));
    묶음붙이기('groups3', 'delta3', 'delta-out3', gr.filter(g => g['종류'] === '조건 3개'));
  }
  마지막gr = gr;
  if (gr && gr.length) {
    그림_찾음(gr, '조건 2개', 'chart-find2', 'find2-wrap');
    그림_찾음(gr, '조건 3개', 'chart-find3', 'find3-wrap');
  }
  그림_curve(cv);
}

(async function () {
  기본옵션();
  단추묶기();
  const [nd, 목록, 데모] = await Promise.all(
    [읽기('nday.json'), 읽기('창목록.json'), 읽기('demo_2일.json')]);
  그림_nday(nd);          // 창과 무관하므로 한 번만 그림
  그림_demo(데모);        // 돌려보기도 2일 창 하나뿐이라 한 번만

  const 창들 = (목록 && 목록['창']) || ['14일'];
  const 탭 = document.getElementById('window-tabs');
  if (탭) {
    탭.innerHTML = 창들.map(c =>
      `<button type="button" role="tab" data-창="${c}" aria-selected="false">평가 ${c}</button>`
    ).join('');
    탭.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (b) 창그리기(b.dataset.창);
    });
    // 창이 하나뿐이면 고를 게 없으니 단추를 숨김
    탭.classList.toggle('hidden', 창들.length < 2);
  }
  await 창그리기((목록 && 목록['기본']) || 창들[0]);
})();
