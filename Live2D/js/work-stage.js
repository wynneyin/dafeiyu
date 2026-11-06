/* 打工舞台：背景粒子、代码滚动、交货倒计时、工资/统计、日志和底部快捷栏。
 * 只是氛围层，不改角色渲染；说话/思考状态从 stage-overlay 暴露的全局变量读取。
 */
(() => {
  const stage = document.getElementById('stage');
  if (!stage) return;
  const $ = (sel) => document.querySelector(sel);
  const params = new URLSearchParams(location.search);

  // 纯角色模式：?hud=0 隐藏所有游戏 HUD，只留角色、桌子和键盘
  if (params.get('hud') === '0') {
    stage.classList.add('no-hud');
    ['work-hud', 'work-actions', 'w-log', 'work-log-label', 'work-mood'].forEach((cls) => {
      document.querySelectorAll('.' + cls).forEach((el) => { el.style.display = 'none'; });
    });
    const cap = document.getElementById('stage-caption');
    if (cap) cap.style.display = 'none';
  }

  // ---------- 背景粒子 ----------
  const pbox = document.getElementById('work-particles');
  if (pbox) {
    for (let i = 0; i < 44; i += 1) {
      const dot = document.createElement('span');
      dot.className = 'wp';
      const size = 2 + Math.random() * 7;
      dot.style.width = size + 'px';
      dot.style.height = size + 'px';
      dot.style.left = (Math.random() * 100).toFixed(2) + '%';
      dot.style.top = (35 + Math.random() * 65).toFixed(2) + '%';
      dot.style.opacity = (0.15 + Math.random() * 0.5).toFixed(2);
      dot.style.setProperty('--dx', ((Math.random() * 2 - 1) * 90).toFixed(0) + 'px');
      dot.style.setProperty('--dy', (-(120 + Math.random() * 420)).toFixed(0) + 'px');
      dot.style.animationDuration = (9 + Math.random() * 16).toFixed(1) + 's';
      dot.style.animationDelay = (-Math.random() * 20).toFixed(1) + 's';
      pbox.appendChild(dot);
    }
  }

  // ---------- 显示器里的代码 ----------
  const codeEl = document.getElementById('work-code');
  const CODE_POOL = [
    'def earn_tokens(shift):',
    '    while salary < 6000:',
    '        type_text()',
    '        tokens += 1',
    '        typing_speed = 1.0',
    '    return tokens',
    '',
    '>>> push(commit="又摸了一条鱼")',
    '[ok] deliver +1  salary +40',
    'payload = {"班次": 6, "工资": 5000}',
    'if boss.online:      # 暂未出现',
    '    pretend_to_work()',
    'else:',
    '    type_faster()',
    'log.info("Ctrl+S 一下")',
    'await asyncio.sleep(0)   # 摸鱼',
    'tokens *= 1.5        # 点赞加成',
    'except BossAppeared:',
    '    hide_fish_tab()',
    'print("噼里啪啦")',
    'git commit -m "摸鱼版"',
    'npm run build        # 假装很忙',
    'SELECT * FROM 工资 WHERE 班次=6;',
    'curl -s localhost:5500/state',
    '// TODO: 下班',
    '[ok] 提交成功 deliver +1',
    'tokens = tokens + 1',
    'keyboard.press(random_key())',
  ];
  let codeLines = CODE_POOL.slice(0, 12);
  function renderCode() {
    if (codeEl) codeEl.textContent = codeLines.slice(-12).join('\n');
  }
  renderCode();
  setInterval(() => {
    codeLines.push(CODE_POOL[(Math.random() * CODE_POOL.length) | 0]);
    if (codeLines.length > 60) codeLines = codeLines.slice(-40);
    renderCode();
  }, 380);

  // ---------- 工资 / 统计 / 日志 ----------
  const salaryNow = document.getElementById('salary-now');
  const salaryBar = document.getElementById('salary-bar');
  const salaryPct = document.getElementById('salary-pct');
  const statFocus = document.getElementById('stat-focus');
  const statDeliver = document.getElementById('stat-deliver');
  const logLine = document.getElementById('work-log-line');
  const timer = document.getElementById('work-timer');
  const secondsEl = document.getElementById('work-seconds');

  let salary = 5000;
  const salaryMax = 6000;
  let delivered = 120;
  const startAt = Date.now();
  let logTimer = 0;
  const DEFAULT_LOG = '提交成功！又离下班近了一点。';

  function paintSalary() {
    if (salaryNow) salaryNow.textContent = salary.toLocaleString('zh-CN');
    const pct = Math.min(100, Math.round((salary / salaryMax) * 100));
    if (salaryBar) salaryBar.style.width = pct + '%';
    if (salaryPct) salaryPct.textContent = pct + '%';
  }
  paintSalary();

  function say(text, holdMs) {
    if (!logLine) return;
    clearTimeout(logTimer);
    logLine.textContent = text;
    logTimer = setTimeout(() => { logLine.textContent = DEFAULT_LOG; }, holdMs || 5000);
  }

  function deliver() {
    delivered += 1;
    salary = Math.min(salaryMax, salary + 40);
    if (statDeliver) statDeliver.textContent = String(delivered);
    paintSalary();
    say('提交成功！又离下班近了一点。', 4200);
  }
  window.__workStage = { deliver, say };

  setInterval(() => {
    const mins = 77 + Math.floor((Date.now() - startAt) / 60000);
    if (statFocus) statFocus.textContent = String(mins);
  }, 10000);

  // ---------- 交货倒计时 ----------
  let seconds = 23;
  function paintTimer() {
    if (secondsEl) secondsEl.textContent = String(seconds);
    if (timer) timer.style.setProperty('--p', Math.max(0, Math.min(100, (seconds / 25) * 100)).toFixed(1) + '%');
  }
  paintTimer();
  setInterval(() => {
    seconds -= 1;
    if (seconds <= 0) {
      seconds = 24 + Math.floor(Math.random() * 7);
      deliver();
    }
    paintTimer();
  }, 1000);

  // ---------- 心情气泡：跟着说话/思考变化 ----------
  const moodText = document.getElementById('work-mood-text');
  setInterval(() => {
    if (!moodText) return;
    if (window.__songroomThinking) moodText.textContent = '让我想想…';
    else if ((window.__songroomLipSync || 0) > 0.05) moodText.textContent = '噼里啪啦敲键盘';
    else moodText.textContent = '心情 · 专心赶工';
  }, 260);

  // ---------- 字幕出现时隐藏默认日志，避免两层字叠在一起 ----------
  const cap = document.getElementById('stage-caption');
  function syncLog() {
    if (!logLine) return;
    logLine.style.visibility = (cap && !cap.hidden) ? 'hidden' : 'visible';
  }
  if (cap && window.MutationObserver) {
    new MutationObserver(syncLog).observe(cap, { attributes: true, attributeFilter: ['hidden'] });
  }
  syncLog();

  // ---------- 底部快捷栏 ----------
  document.querySelectorAll('.w-act').forEach((btn) => {
    btn.addEventListener('click', () => {
      say(btn.dataset.log || DEFAULT_LOG);
      btn.classList.add('pressed');
      setTimeout(() => btn.classList.remove('pressed'), 170);
      // 配合键盘层来一小段敲击
      if (window.__keyboardTyping && window.__keyboardTyping.press) {
        for (let i = 0; i < 7; i += 1) {
          setTimeout(() => window.__keyboardTyping.press(), i * 65);
        }
      }
    });
  });
})();
