/* 生命层 v1 —— 表现层欠账 P1/P2/P3 + 版本可见 + 体检面板
 * 独立脚本：零外部素材、零 API 依赖，断网、服务没起来也照常生效。
 * 这样"改了能不能看到"不再取决于大脑有没有连上。
 */
(function () {
  'use strict';
  var BUILD = '2026-11-14-b';
  var $ = function (id) { return document.getElementById(id); };
  var hw = document.querySelector('.headwrap');
  var kParam = (function () {
    var m = /[?&]k=([^&]*)/.exec(location.search);
    return m ? decodeURIComponent(m[1]) : null;
  })();
  var host = location.hostname;
  var brainBase = location.protocol + '//' + host + ':8765';
  var withKey = function (u) { return u + (kParam ? (u.indexOf('?') >= 0 ? '&' : '?') + 'k=' + encodeURIComponent(kParam) : ''); };

  /* ---------- 1. 海底场景：她得待在一个地方 ---------- */
  var sea = $('sea');
  var ctx = sea && sea.getContext ? sea.getContext('2d') : null;
  var W = 0, H = 0, last = 0;
  var grass = [], motes = [], fishlets = [];

  function seed() {
    grass = []; motes = []; fishlets = [];
    var i;
    for (i = 0; i < 18; i++) grass.push({
      x: Math.random() * W, h: 60 + Math.random() * 170,
      w: 3 + Math.random() * 5, p: Math.random() * 6.28, c: i % 3
    });
    for (i = 0; i < 46; i++) motes.push({
      x: Math.random() * W, y: Math.random() * H,
      r: 0.6 + Math.random() * 1.8, s: 4 + Math.random() * 14, p: Math.random() * 6.28
    });
    for (i = 0; i < 9; i++) fishlets.push({
      x: Math.random() * W, y: H * 0.16 + Math.random() * H * 0.46,
      s: 3 + Math.random() * 6, v: 6 + Math.random() * 14, p: Math.random() * 6.28
    });
  }

  function resize() {
    if (!sea) return;
    W = sea.width = Math.max(320, window.innerWidth);
    H = sea.height = Math.max(320, window.innerHeight);
    seed();
  }
  window.addEventListener('resize', resize);
  resize();

  function draw(t) {
    if (!ctx || t - last < 0.075) return;      // 约 13fps，不抢主渲染
    last = t;
    var g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, '#123b5a'); g.addColorStop(0.45, '#0b2a42'); g.addColorStop(1, '#061521');
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);

    var i, bx, lg;
    for (i = 0; i < 4; i++) {                  // 水面斜射光柱
      bx = W * (0.14 + i * 0.24) + Math.sin(t * 0.22 + i) * 38;
      lg = ctx.createLinearGradient(bx, 0, bx + 130, H * 0.9);
      lg.addColorStop(0, 'rgba(150,225,255,0.16)');
      lg.addColorStop(1, 'rgba(150,225,255,0)');
      ctx.fillStyle = lg;
      ctx.beginPath();
      ctx.moveTo(bx - 26, 0); ctx.lineTo(bx + 46, 0);
      ctx.lineTo(bx + 150, H * 0.92); ctx.lineTo(bx + 30, H * 0.92);
      ctx.closePath(); ctx.fill();
    }

    ctx.fillStyle = 'rgba(120,190,225,0.13)';  // 远处小鱼群
    for (i = 0; i < fishlets.length; i++) {
      var f = fishlets[i];
      f.x += f.v * 0.075;
      if (f.x > W + 30) f.x = -30;
      var fy = f.y + Math.sin(t * 0.7 + f.p) * 7;
      ctx.beginPath();
      if (ctx.ellipse) ctx.ellipse(f.x, fy, f.s * 1.7, f.s * 0.62, 0, 0, 6.28);
      else ctx.arc(f.x, fy, f.s, 0, 6.28);
      ctx.fill();
      ctx.beginPath();
      ctx.moveTo(f.x + f.s * 1.4, fy);
      ctx.lineTo(f.x + f.s * 2.5, fy - f.s * 0.7);
      ctx.lineTo(f.x + f.s * 2.5, fy + f.s * 0.7);
      ctx.closePath(); ctx.fill();
    }

    var sand = ctx.createLinearGradient(0, H * 0.82, 0, H);
    sand.addColorStop(0, 'rgba(24,58,74,0)');
    sand.addColorStop(1, 'rgba(38,74,84,0.85)');
    ctx.fillStyle = sand;
    ctx.beginPath(); ctx.moveTo(0, H);
    for (var x = 0; x <= W; x += 40) ctx.lineTo(x, H * 0.88 + Math.sin(x * 0.006 + t * 0.1) * 12);
    ctx.lineTo(W, H); ctx.closePath(); ctx.fill();

    var cols = ['rgba(46,120,110,0.55)', 'rgba(38,100,120,0.5)', 'rgba(58,132,108,0.42)'];
    for (i = 0; i < grass.length; i++) {       // 摆动的水草
      var q = grass[i];
      var sway = Math.sin(t * 0.9 + q.p) * 18;
      ctx.strokeStyle = cols[q.c]; ctx.lineWidth = q.w; ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(q.x, H);
      ctx.quadraticCurveTo(q.x + sway * 0.5, H - q.h * 0.55, q.x + sway, H - q.h);
      ctx.stroke();
    }

    ctx.fillStyle = 'rgba(190,235,255,0.35)';  // 悬浮微粒
    for (i = 0; i < motes.length; i++) {
      var m = motes[i];
      m.y -= m.s * 0.075;
      if (m.y < -5) { m.y = H + 5; m.x = Math.random() * W; }
      ctx.beginPath(); ctx.arc(m.x + Math.sin(t * 0.5 + m.p) * 6, m.y, m.r, 0, 6.28); ctx.fill();
    }
  }
  function tick(ts) { draw(ts / 1000); requestAnimationFrame(tick); }
  if (ctx) requestAnimationFrame(tick);

  /* ---------- 2. 表情：不靠服务端也会自己变 ---------- */
  var EMO_LABEL = {
    idle: '发呆', listen: '在听', think: '想事情', happy: '开心', love: '喜欢',
    shy: '害羞', angry: '炸毛', surprise: '吓一跳', sad: '委屈', confused: '疑惑',
    sleepy: '困了', proud: '得意', expect: '期待', smug: '哼哼', relief: '松口气',
    serious: '认真', nervous: '紧张', hungry: '饿了'
  };
  var tag = document.createElement('div');
  tag.id = 'emoTag'; document.body.appendChild(tag);
  var tagUntil = 0, lastEmo = '';
  function showTag(name) {
    tag.textContent = EMO_LABEL[name] || name;
    tag.className = 'on';
    tagUntil = performance.now() + 1700;
  }
  var idleSet = ['happy', 'think', 'sleepy', 'surprise', 'love', 'proud', 'idle', 'shy'];
  function wanderEmotion() {
    if (typeof setEmotion === 'function') {
      var name = idleSet[Math.floor(Math.random() * idleSet.length)];
      setEmotion(name, 5200);
      showTag(name);
    }
    setTimeout(wanderEmotion, 7000 + Math.random() * 7000);
  }
  setTimeout(wanderEmotion, 3200);

  // 现有页面里的 emotion 是全局 let；轮询它，服务端切表情时也亮标签
  setInterval(function () {
    var e = (typeof emotion !== 'undefined') ? emotion : '';
    if (e && e !== lastEmo) { lastEmo = e; showTag(e); }
    if (performance.now() > tagUntil) tag.className = '';
  }, 220);

  /* ---------- 3. 真互动：戳一下、拖一下 ---------- */
  var bubble = document.createElement('div');
  bubble.id = 'pokeBubble'; document.body.appendChild(bubble);
  var bubbleUntil = 0;
  var pokeLines = ['别戳啦，本鲸会痒。', '嗯？', '再戳要收白饭了。', '干嘛呀。', '本鲸在呢。'];
  function sayLocal(s) {
    bubble.textContent = s; bubble.className = 'on';
    bubbleUntil = performance.now() + 2000;
    setTimeout(function () { if (performance.now() >= bubbleUntil) bubble.className = ''; }, 2100);
  }
  function poke() {
    if (typeof setEmotion === 'function') setEmotion('surprise', 2400);
    showTag('surprise');
    sayLocal(pokeLines[Math.floor(Math.random() * pokeLines.length)]);
    if (hw && hw.animate) {
      hw.animate([{ transform: 'scale(1)' }, { transform: 'scale(1.045)' }, { transform: 'scale(1)' }],
        { duration: 420, easing: 'ease-out' });
    }
  }

  var dragging = false, sx = 0, sy = 0, ox = 0, oy = 0, cx = 0, cy = 0;
  function dragStart(x, y) { dragging = true; sx = x; sy = y; ox = cx; oy = cy; if (hw) hw.style.transition = 'none'; }
  function dragMove(x, y) {
    if (!dragging || !hw) return;
    cx = Math.max(-220, Math.min(220, ox + x - sx));
    cy = Math.max(-160, Math.min(160, oy + y - sy));
    hw.style.transform = 'translate(' + cx + 'px,' + cy + 'px)';
  }
  function dragEnd() {
    if (!dragging) return;
    dragging = false;
    if (hw) { hw.style.transition = 'transform .5s cubic-bezier(.2,1.4,.4,1)'; hw.style.transform = 'translate(0,0)'; }
    cx = 0; cy = 0; poke();
  }
  if (hw) {
    hw.style.transition = 'transform .5s cubic-bezier(.2,1.4,.4,1)';
    if (window.PointerEvent) {
      hw.addEventListener('pointerdown', function (e) {
        dragStart(e.clientX, e.clientY);
        if (hw.setPointerCapture) { try { hw.setPointerCapture(e.pointerId); } catch (err) {} }
      });
      window.addEventListener('pointermove', function (e) { dragMove(e.clientX, e.clientY); });
      window.addEventListener('pointerup', dragEnd);
    } else {
      hw.addEventListener('mousedown', function (e) { dragStart(e.clientX, e.clientY); });
      hw.addEventListener('touchstart', function (e) {
        var t = e.touches[0]; if (t) dragStart(t.clientX, t.clientY);
      }, { passive: true });
      window.addEventListener('mousemove', function (e) { dragMove(e.clientX, e.clientY); });
      window.addEventListener('touchmove', function (e) {
        var t = e.touches[0]; if (t) dragMove(t.clientX, t.clientY);
      }, { passive: true });
      window.addEventListener('mouseup', dragEnd);
      window.addEventListener('touchend', dragEnd);
    }
  }

  /* ---------- 4. 版本角标 + 体检面板：改了到底有没有生效，一眼可验 ---------- */
  var buildTag = document.createElement('div');
  buildTag.id = 'buildTag'; buildTag.textContent = 'v ' + BUILD;
  document.body.appendChild(buildTag);

  var panel = document.createElement('div');
  panel.id = 'doctorPanel'; document.body.appendChild(panel);

  function row(name, value, ok) {
    return '<div class="drow"><span>' + name + '</span><b class="' + (ok ? 'ok' : 'off') + '">' + value + '</b></div>';
  }
  function doctor() {
    var yes = function (v) { return typeof v !== 'undefined' && !!v; };
    var h = '<div class="dhead">体检 · 前端 ' + BUILD + '<span id="doctorClose">×</span></div>';
    h += row('前端构建', BUILD, true);
    h += row('页面主机', host, true);
    h += row('大脑连接', (typeof wsReady !== 'undefined' && wsReady) ? '已连上' : '未连接',
      yes(typeof wsReady !== 'undefined' && wsReady));
    h += row('形象 rig', (typeof rigReady !== 'undefined' && rigReady) ? '已加载' : '未加载',
      yes(typeof rigReady !== 'undefined' && rigReady));
    h += row('海底场景', ctx ? '已绘制' : '不可用', !!ctx);
    h += row('表情系统', typeof setEmotion === 'function' ? '就绪' : '缺失', typeof setEmotion === 'function');
    h += row('动作系统', typeof ACT_W !== 'undefined' ? '就绪' : '缺失', typeof ACT_W !== 'undefined');
    h += row('戳 / 拖拽', hw ? '就绪' : '缺失', !!hw);
    h += row('麦克风', navigator.mediaDevices ? '可用' : '不可用（打字模式）', !!navigator.mediaDevices);
    h += '<div class="drow" id="srvRow"><span>服务端</span><b class="off">读取中…</b></div>';
    h += '<div class="dtip">这一页只报告真实状态；红项就是缺的东西。</div>';
    panel.innerHTML = h;
    panel.className = 'on';
    var close = $('doctorClose');
    if (close) close.onclick = function () { panel.className = ''; };
    fetch(withKey(brainBase + '/health'), { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var el = $('srvRow');
        if (el) el.innerHTML = '<span>服务端</span><b class="ok">已运行 · ' +
          (d.features || []).length + ' 项功能 · ' +
          String(d.web_build || d.code_hash || '').slice(0, 12) + '</b>';
      })
      .catch(function () {
        var el = $('srvRow');
        if (el) el.innerHTML = '<span>服务端</span><b class="off">没起来（她现在是离线画面）</b>';
      });
  }
  buildTag.onclick = doctor;

  var toolbar = document.createElement('div');
  toolbar.id = 'toolBar';
  toolbar.innerHTML = '<button data-a="poke">戳一下</button>' +
    '<button data-a="starmap">看记忆</button>' +
    '<button data-a="bad">这句不像她</button>' +
    '<button data-a="doctor">体检</button>';
  document.body.appendChild(toolbar);
  toolbar.addEventListener('click', function (e) {
    var a = e.target && e.target.getAttribute ? e.target.getAttribute('data-a') : '';
    if (a === 'poke') poke();
    if (a === 'starmap') window.open(withKey(brainBase + '/starmap'), '_blank');
    if (a === 'doctor') doctor();
    if (a === 'bad') {
      var sock = (typeof ws !== 'undefined') ? ws : null;
      if (sock && sock.readyState === 1) {
        sock.send(JSON.stringify({ type: 'feedback' }));
        sayLocal('记下了，这句以后不当教材。');
      } else {
        sayLocal('她没连上，等连上再点这个。');
      }
    }
  });
})();
