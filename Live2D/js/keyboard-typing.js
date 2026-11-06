/* 舞台键盘层：一直噼里啪啦敲键盘的社畜鱼形象。
 *
 * 视觉：底部前景一台透视键盘，按键随机亮起。
 * 声音：WebAudio 合成敲击声（无需音频文件），跟说话状态联动。
 *
 * 状态来源：
 *   window.__songroomLipSync —— 核心真实播放音量（0~1），>0.05 视为正在说话
 *   window.__songroomThinking —— 5500 思考信号，由 stage-overlay.js 暴露
 *   window.__stageCaption.state —— 字幕逐字播放状态，兜底判断
 *
 * 可调参数（URL query）：
 *   keys=0        隐藏键盘
 *   keysound=0    静音
 *   kbsize=1.2    键盘缩放（0.5~1.6）
 *   kbbottom=-40  距离底部像素
 */
(() => {
  const params = new URLSearchParams(location.search);
  if (params.get('keys') === '0') return;

  const stage = document.getElementById('stage');
  if (!stage) return;

  const portrait = String(stage.dataset.layout || '').includes('portrait');
  const soundOn = params.get('keysound') !== '0';
  const scale = Number(params.get('kbsize')) || (portrait ? 0.64 : 0.95);
  const bottom = params.has('kbbottom') ? Number(params.get('kbbottom')) : (portrait ? 10 : -42);

  const style = document.createElement('style');
  style.textContent = `
  #kt-desk{position:absolute;left:50%;z-index:3;pointer-events:none;
    bottom:${bottom}px;transform:translateX(-50%) scale(${scale});transform-origin:50% 100%;perspective:1100px}
  #kt-board{position:relative;width:820px;height:250px;transform:rotateX(33deg);
    border-radius:22px;border:2px solid #2b6191;
    background:linear-gradient(180deg,#12365e 0%,#0a2342 55%,#071a33 100%);
    box-shadow:0 24px 48px rgba(0,10,25,.5),inset 0 2px 0 rgba(130,210,255,.28),inset 0 -14px 30px rgba(0,8,20,.55)}
  #kt-keys{position:absolute;inset:24px 26px 26px;display:flex;flex-direction:column;gap:8px}
  .kt-row{display:flex;gap:8px;flex:1}
  .kt-key{flex:1;border-radius:8px;
    background:linear-gradient(180deg,#35668f 0%,#1d4568 60%,#153757 100%);
    box-shadow:0 4px 0 #0a2340,inset 0 1px 0 rgba(170,225,255,.35);
    transition:background .05s linear,box-shadow .05s linear,transform .05s linear}
  .kt-key.down{transform:translateY(3px);
    background:linear-gradient(180deg,#a6ecff 0%,#4aa6d8 60%,#2f7fb8 100%);
    box-shadow:0 0 0 #0a2340,0 0 22px rgba(120,220,255,.55),inset 0 1px 0 rgba(255,255,255,.6)}
  #kt-led{position:absolute;right:26px;top:11px;width:10px;height:10px;border-radius:50%;
    background:#2b5b7f;transition:background .12s,box-shadow .12s}
  #kt-led.on{background:#7fe6ff;box-shadow:0 0 12px #7fe6ff}
  `;
  document.head.appendChild(style);

  const desk = document.createElement('div');
  desk.id = 'kt-desk';
  const board = document.createElement('div');
  board.id = 'kt-board';
  const keysEl = document.createElement('div');
  keysEl.id = 'kt-keys';
  const led = document.createElement('div');
  led.id = 'kt-led';
  board.appendChild(keysEl);
  board.appendChild(led);
  desk.appendChild(board);
  stage.appendChild(desk);

  // 5 行，每行总宽度都是 14 个单位，宽键用更大 flex 值
  const ROWS = [
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2],
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 3],
    [2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 3],
    [2, 6, 2, 2, 2],
  ];

  const keys = [];
  ROWS.forEach((units) => {
    const row = document.createElement('div');
    row.className = 'kt-row';
    units.forEach((u) => {
      const key = document.createElement('div');
      key.className = 'kt-key';
      key.style.flex = String(u);
      row.appendChild(key);
      keys.push(key);
    });
    keysEl.appendChild(row);
  });

  // ---------- 敲击音效：合成的短噪声 + 低频 thock ----------
  let actx = null;
  let noiseBufs = [];
  let muted = !soundOn;

  function initAudio() {
    if (muted) return null;
    if (!actx) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return null;
      try { actx = new Ctx(); } catch { return null; }
      for (let v = 0; v < 3; v += 1) {
        const n = Math.floor(actx.sampleRate * 0.045);
        const buf = actx.createBuffer(1, n, actx.sampleRate);
        const data = buf.getChannelData(0);
        let last = 0;
        for (let i = 0; i < n; i += 1) {
          const env = Math.pow(1 - i / n, 2.6);
          last = last * 0.55 + (Math.random() * 2 - 1) * 0.45;
          data[i] = last * env;
        }
        noiseBufs.push(buf);
      }
    }
    if (actx.state === 'suspended') actx.resume().catch(() => {});
    return actx;
  }

  function click() {
    const ctx = initAudio();
    if (!ctx || muted || ctx.state !== 'running') return;
    const t = ctx.currentTime;

    const src = ctx.createBufferSource();
    src.buffer = noiseBufs[(Math.random() * noiseBufs.length) | 0];
    const band = ctx.createBiquadFilter();
    band.type = 'bandpass';
    band.frequency.value = 1500 + Math.random() * 1800;
    band.Q.value = 0.7;
    const gain = ctx.createGain();
    gain.gain.value = 0.09 + Math.random() * 0.05;
    src.connect(band).connect(gain).connect(ctx.destination);
    src.start(t);
    src.stop(t + 0.06);

    const osc = ctx.createOscillator();
    osc.type = 'triangle';
    osc.frequency.value = 105 + Math.random() * 45;
    const og = ctx.createGain();
    og.gain.setValueAtTime(0.03, t);
    og.gain.exponentialRampToValueAtTime(0.001, t + 0.05);
    osc.connect(og).connect(ctx.destination);
    osc.start(t);
    osc.stop(t + 0.06);
  }

  // OBS 浏览器源一般允许自动播放；普通浏览器里第一次点击后才会出声
  initAudio();
  ['pointerdown', 'keydown', 'touchstart'].forEach((evt) => {
    addEventListener(evt, () => initAudio(), { passive: true });
  });
  setInterval(() => {
    if (actx && actx.state === 'suspended') actx.resume().catch(() => {});
  }, 5000);

  // ---------- 敲击节奏 ----------
  let ledTimer = 0;

  function press() {
    const key = keys[(Math.random() * keys.length) | 0];
    key.classList.add('down');
    setTimeout(() => key.classList.remove('down'), 70 + Math.random() * 50);
    led.classList.add('on');
    clearTimeout(ledTimer);
    ledTimer = setTimeout(() => led.classList.remove('on'), 140);
    click();
  }

  const speaking = () => (window.__songroomLipSync || 0) > 0.05;
  const thinking = () => !!window.__songroomThinking;

  let nextClickAt = 0;
  let burstEnd = 0;
  let nextBurstAt = performance.now() + 1200;

  function loop(now) {
    const talk = speaking();
    const think = thinking();
    // 打工舞台要求「一直在打字」：页面把 window.__keyboardAlwaysTyping 设为 true
    const always = !!window.__keyboardAlwaysTyping;

    // 不说话时也要时不时来一小段敲击，维持「一直在打字」的感觉
    if (!always && !talk && !think && now > nextBurstAt && now > burstEnd) {
      burstEnd = now + 450 + Math.random() * 1000;
      nextBurstAt = burstEnd + 2200 + Math.random() * 4200;
    }

    const active = always || talk || think || now < burstEnd;
    if (active && now >= nextClickAt) {
      press();
      const cps = talk ? 11 + Math.random() * 6 : (think || always ? 7.5 : 9);
      nextClickAt = now + 1000 / cps;
    } else if (!active) {
      nextClickAt = now + 40;
    }
    requestAnimationFrame(loop);
  }

  window.__keyboardTyping = { press, speaking, thinking };
  requestAnimationFrame(loop);
})();
