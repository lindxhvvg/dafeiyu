/* 大肥鱼 rig —— 33 层立绘渲染器
 * 素材：dsh-dfy character-packs/default-whale
 *       角色 © 上善无形 (Bilibili UID 4456176)，CC BY-NC-SA 4.0
 *       仅限个人非商业使用；再分发需署名并保持相同许可
 * 设计坐标系 1280x1280，坐标取自 manifest.json
 */
(function (global) {
  'use strict';

  // 从后到前的叠放顺序（hair-back 整图不用，用 5 块拆分件便于摆发）
  const ORDER = [
    'hair-back-center',
    'hair-back-inner-left', 'hair-back-inner-right',
    'hair-back-outer-left', 'hair-back-outer-right',
    'tail', 'whale-fins',
    'leg-left', 'leg-right', 'shoe-left', 'shoe-right',
    'skirt', 'collar-front', 'torso', 'torso-bow',
    'arm-left-sleeve', 'hand-left-rest-side', 'arm-right',
    'neck', 'human-ears', 'face', 'mouth',
    'eye-white-left', 'eye-white-right',
    'iris-left', 'iris-right',
    'lash-left', 'lash-right',
    'brow-left', 'brow-right',
    'hair-front', 'side-bow', 'maid-headband', 'ahoge'
  ];

  // 眼睛包围盒（eye-white + lash 的并集，用于缩放锚点）
  const EYE = {
    left:  { x: 495, y: 331, w: 96, h: 92 },
    right: { x: 660, y: 331, w: 100, h: 92 },
    irisL: { x: 529, y: 357, w: 56, h: 62 },
    irisR: { x: 666, y: 357, w: 58, h: 62 }
  };
  // 头部统一旋转轴心（脖子根部）
  const NECK = { x: 640, y: 505 };

  let MANIFEST = null;
  const IMGS = {};
  const MISSING = [];

  function load(base) {
    return fetch(base + 'manifest.json')
      .then(r => r.json())
      .then(m => {
        MANIFEST = m;
        const files = new Set(Object.values(m.parts).map(p => p.file));
        return Promise.all([...files].map(f => new Promise(res => {
          const im = new Image();
          im.onload = () => { IMGS[f] = im; res(); };
          im.onerror = () => { MISSING.push(f); res(); };
          im.src = base + f;
        })));
      });
  }

  /* ---------- 情绪预设 ----------
   * 这个角色的刘海盖住眉毛，所以表情全靠「眼形 + 嘴 + 腮红 + 特效」
   * eyeY  垂直开合（1=原样，0.1=眯成缝，1.2=睁大）
   * eyeX  水平开合
   * eyeDy 眼睛整体上下偏移
   * irisY 瞳仁垂直缩放（难过时瞳仁放大显得可怜）
   */
  const EMOTION = {
    idle:     { eyeY: 1.00, eyeX: 1.00, eyeDy: 0,  irisS: 1.00, mouth: 'smile',  blush: 0.00, fx: null },
    // 在听你说话：眼睛睁大、嘴闭着，不抢话
    listen:   { eyeY: 1.10, eyeX: 1.01, eyeDy: 0,  irisS: 1.05, mouth: 'small',  blush: 0.06, fx: null },
    // 在想事情：眼睛微微往上看，嘴闭着
    think:    { eyeY: 0.94, eyeX: 1.00, eyeDy: -4, irisS: 1.02, mouth: 'small',  blush: 0.05, fx: null },
    happy:    { eyeY: 0.58, eyeX: 1.02, eyeDy: 5,  irisS: 0.96, mouth: 'smile',  blush: 0.32, fx: null },
    love:     { eyeY: 0.52, eyeX: 1.02, eyeDy: 6,  irisS: 0.94, mouth: 'smile',  blush: 0.88, fx: 'heart' },
    shy:      { eyeY: 0.66, eyeX: 0.98, eyeDy: 4,  irisS: 0.96, mouth: 'small',  blush: 0.72, fx: null },
    angry:    { eyeY: 0.84, eyeX: 0.92, eyeDy: -3, irisS: 0.90, mouth: 'frown',  blush: 0.12, fx: 'anger' },
    surprise: { eyeY: 1.20, eyeX: 1.07, eyeDy: -1, irisS: 1.08, mouth: 'open',   blush: 0.14, fx: 'excl' },
    sad:      { eyeY: 0.78, eyeX: 1.00, eyeDy: 6,  irisS: 1.12, mouth: 'frown',  blush: 0.06, fx: 'tear' },
    confused: { eyeY: 0.94, eyeX: 1.00, eyeDy: 2,  irisS: 1.00, mouth: 'small',  blush: 0.10, fx: 'question' },
    sleepy:   { eyeY: 0.12, eyeX: 1.00, eyeDy: 0,  irisS: 0.60, mouth: 'small',  blush: 0.20, fx: 'zzz' },
    proud:    { eyeY: 0.70, eyeX: 1.00, eyeDy: 3,  irisS: 0.92, mouth: 'smirk',  blush: 0.22, fx: null },
    expect:   { eyeY: 1.14, eyeX: 1.04, eyeDy: 0,  irisS: 1.14, mouth: 'open',   blush: 0.34, fx: 'star' },
    smug:     { eyeY: 0.60, eyeX: 1.00, eyeDy: 4,  irisS: 0.88, mouth: 'smirk',  blush: 0.26, fx: null },
    relief:   { eyeY: 0.50, eyeX: 1.00, eyeDy: 5,  irisS: 0.94, mouth: 'smile',  blush: 0.28, fx: null },
    serious:  { eyeY: 0.92, eyeX: 1.00, eyeDy: 0,  irisS: 0.94, mouth: 'small',  blush: 0.00, fx: null },
    nervous:  { eyeY: 1.04, eyeX: 0.98, eyeDy: 1,  irisS: 1.06, mouth: 'small',  blush: 0.52, fx: 'sweat' },
    hungry:   { eyeY: 1.10, eyeX: 1.02, eyeDy: 0,  irisS: 1.08, mouth: 'open',   blush: 0.40, fx: 'rice' }
  };

  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }

  function draw(ctx, st) {
    const m = MANIFEST;
    if (!m) return;
    const D = m.designSize[0];
    ctx.clearRect(0, 0, D, D);

    const e = EMOTION[st.emotion] || EMOTION.idle;
    const t = st.t || 0;
    const ang = st.look || 0;              // -1..1 转头
    const voice = st.voice || 0;           // 0..1 说话音量
    const blink = st.blink == null ? 1 : st.blink;

    // 呼吸：整体极轻微起伏
    const breath = Math.sin(t * 0.0021);

    // 头部整体偏移/旋转
    const headDx = ang * 10;
    const headDy = Math.abs(ang) * 2.0 - 1.5;
    const headRot = ang * 1.4 * Math.PI / 180;

    ctx.save();
    ctx.translate(D / 2, 1246);
    // wiggle：撒娇时整个人左右扭
    const wig = st.action === 'wiggle' ? Math.sin(t * 0.0075) * 1.1 : 0;
    ctx.rotate(ang * 0.014 + wig * Math.PI / 180);
    ctx.scale(1 + breath * 0.0022, 1 + breath * 0.0022);
    ctx.translate(-D / 2, -1246);

    const S = { ang, e, voice, t, breath, blink, headDx, headDy, headRot,
                gazeX: (st.gazeX || 0), gazeY: (st.gazeY || 0),
                action: st.action || 'none' };

    for (const name of ORDER) {
      const p = m.parts[name];
      if (!p || !IMGS[p.file]) continue;
      drawPart(ctx, name, p, IMGS[p.file], S);
    }

    // 特效层（画在最后，最前面）
    drawFx(ctx, e.fx, t, e, ang);

    ctx.restore();
  }

  const HEAD_RE = /^(face|mouth|eye-|iris-|lash-|brow-|hair-front|human-ears|maid-headband|ahoge|side-bow|whale-fins)/;

  function drawPart(ctx, name, p, img, S) {
    const { ang, e, voice, t, blink, headDx, headDy, headRot } = S;
    const x = p.x, y = p.y, w = p.width, h = p.height;
    const isHead = HEAD_RE.test(name);

    // ===== 眼睛（eye-white / lash）=====
    if (name.startsWith('eye-white') || name.startsWith('lash')) {
      const side = name.endsWith('left') ? EYE.left : EYE.right;
      const cx = side.x + side.w / 2, cy = side.y + side.h / 2;
      const openY = clamp(e.eyeY * blink, 0.05, 1.35);
      ctx.save();
      headXform(ctx, S);
      ctx.translate(cx, cy);
      ctx.scale(e.eyeX, openY);
      ctx.translate(-cx, -cy);
      ctx.drawImage(img, 0, 0, img.width, img.height, x, y, w, h);
      ctx.restore();
      return;
    }

    // ===== 瞳仁 =====
    if (name.startsWith('iris')) {
      const isL = name.endsWith('left');
      const ib = isL ? EYE.irisL : EYE.irisR;
      const eb = isL ? EYE.left : EYE.right;
      const ecx = eb.x + eb.w / 2, ecy = eb.y + eb.h / 2;
      const openY = clamp(e.eyeY * blink, 0.05, 1.35);
      // 瞳仁被眼皮带动：按眼皮中线压缩
      ctx.save();
      headXform(ctx, S);
      ctx.translate(ecx, ecy);
      ctx.scale(e.eyeX, openY);
      ctx.translate(-ecx, -ecy);
      // 视线跟随（在眼皮坐标系内平移）
      ctx.translate(S.gazeX * 0.9, S.gazeY * 0.7);
      // 瞳仁自身缩放，锚点=瞳仁中心
      const icx = ib.x + ib.w / 2, icy = ib.y + ib.h / 2;
      ctx.translate(icx, icy);
      ctx.scale(e.irisS, e.irisS);
      ctx.translate(-icx, -icy);
      ctx.drawImage(img, 0, 0, img.width, img.height, x, y, w, h);
      ctx.restore();
      return;
    }

    // ===== 嘴 =====
    if (name === 'mouth') {
      ctx.save();
      headXform(ctx, S);
      drawMouth(ctx, p, img, e.mouth, voice);
      ctx.restore();
      return;
    }

    // ===== 后发摆动 =====
    let dx = 0, dy = 0;
    if (name.startsWith('hair-back')) {
      const k = name.includes('outer') ? 1.7 : name.includes('inner') ? 1.0 : 0.55;
      dx += ang * 5 * k + Math.sin(t * 0.0016 + k * 2) * 1.6 * k;
    }

    // ===== 尾巴 =====
    if (name === 'tail') {
      // wag_fast 摆得急，wag_slow 慢悠悠，睡觉时几乎不动
      const spd = S.action === 'wag_fast' ? 3.1 : S.action === 'wag_slow' ? 1.5
                : S.action === 'sleep' ? 0.3 : 1.0;
      const amp = S.action === 'wag_fast' ? 3.4 : S.action === 'wag_slow' ? 2.0 : 1.2;
      ctx.save();
      rotAround(ctx, p.x + p.width * 0.04, p.y + p.height * 0.16,
                Math.sin(t * 0.0013 * spd) * amp * Math.PI / 180);
      ctx.drawImage(img, 0, 0, img.width, img.height, x, y, w, h);
      ctx.restore();
      return;
    }

    // ===== 呆毛 =====
    if (name === 'ahoge') {
      ctx.save();
      ctx.translate(headDx * 0.6, headDy * 0.4);
      rotAround(ctx, p.x + p.width * 0.5, p.y + p.height * 0.95,
                (Math.sin(t * 0.0022) * 4 + ang * 3) * Math.PI / 180);
      ctx.drawImage(img, 0, 0, img.width, img.height, x, y, w, h);
      ctx.restore();
      return;
    }

    // ===== 手臂轻摆 =====
    if (name === 'arm-left-sleeve' || name === 'hand-left-rest-side' || name === 'arm-right') {
      ctx.save();
      rotAround(ctx, p.x + p.width * 0.5, p.y + 4,
                Math.sin(t * 0.0018 + (name === 'arm-right' ? 0 : 1.2)) * 0.8 * Math.PI / 180);
      ctx.drawImage(img, 0, 0, img.width, img.height, x, y, w, h);
      ctx.restore();
      return;
    }

    // ===== 其余部件 =====
    ctx.save();
    if (isHead) headXform(ctx, S);
    else ctx.translate(dx, dy);
    ctx.drawImage(img, 0, 0, img.width, img.height, x, y, w, h);
    if (name === 'face' && e.blush > 0) drawBlush(ctx, e.blush);
    ctx.restore();
  }

  // 头部整体变换（绕脖子轴心），并把偏移量算进去
  function headXform(ctx, S) {
    ctx.translate(S.headDx, S.headDy);
    if (S.headRot) rotAround(ctx, NECK.x, NECK.y, S.headRot);
  }

  function rotAround(ctx, px, py, rad) {
    ctx.translate(px, py); ctx.rotate(rad); ctx.translate(-px, -py);
  }

  function drawBlush(ctx, a) {
    const spots = [[542, 424], [712, 424]];
    for (const [cx, cy] of spots) {
      const g = ctx.createRadialGradient(cx, cy, 1, cx, cy, 34);
      g.addColorStop(0, 'rgba(255,116,140,' + (0.6 * a) + ')');
      g.addColorStop(0.6, 'rgba(255,130,150,' + (0.32 * a) + ')');
      g.addColorStop(1, 'rgba(255,140,160,0)');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.ellipse(cx, cy, 34, 18, 0, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  /* 嘴：原素材只有一条 47x11 的微笑弧，其余形态现画 */
  function drawMouth(ctx, p, img, kind, voice) {
    const cx = p.x + p.width / 2;
    const cy = p.y + p.height / 2 + 1;
    const open = Math.min(1, voice * 1.3);
    const INK = 'rgba(86,52,62,0.92)';

    ctx.save();
    ctx.translate(cx, cy);

    // 说话时一律优先张嘴
    if (open > 0.10) {
      const w = 20 + open * 13;
      const h = 6 + open * 27;
      ctx.fillStyle = 'rgba(122,54,68,0.96)';
      ctx.beginPath();
      ctx.ellipse(0, 0, w / 2, h / 2, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = 'rgba(230,142,152,0.9)';
      ctx.beginPath();
      ctx.ellipse(0, h * 0.24, w * 0.32, h * 0.24, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
      return;
    }

    switch (kind) {
      case 'smile':
        ctx.drawImage(img, 0, 0, img.width, img.height, -p.width / 2, -p.height / 2, p.width, p.height);
        break;
      case 'small': {
        ctx.strokeStyle = INK;
        ctx.lineWidth = 2.4;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(-7, 0);
        ctx.quadraticCurveTo(0, 3.5, 7, 0);
        ctx.stroke();
        break;
      }
      case 'open': {
        ctx.fillStyle = 'rgba(122,54,68,0.96)';
        ctx.beginPath();
        ctx.ellipse(0, 1, 12, 11, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = 'rgba(230,142,152,0.9)';
        ctx.beginPath();
        ctx.ellipse(0, 5, 6, 4.5, 0, 0, Math.PI * 2);
        ctx.fill();
        break;
      }
      case 'frown': {
        ctx.strokeStyle = INK;
        ctx.lineWidth = 2.4;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(-9, 3);
        ctx.quadraticCurveTo(0, -4, 9, 3);
        ctx.stroke();
        break;
      }
      case 'smirk': {
        ctx.strokeStyle = INK;
        ctx.lineWidth = 2.4;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(-8, 1);
        ctx.quadraticCurveTo(1, 4, 10, -4);
        ctx.stroke();
        break;
      }
      default:
        ctx.drawImage(img, 0, 0, img.width, img.height, -p.width / 2, -p.height / 2, p.width, p.height);
    }
    ctx.restore();
  }

  /* ---------- 情绪特效 ----------
   * 位置参考头部右侧空白，全部矢量绘制，不依赖额外素材
   */
  function drawFx(ctx, fx, t, e, ang) {
    if (!fx) return;
    ctx.save();
    ctx.translate(ang * 10, 0);
    const pulse = 0.85 + Math.sin(t * 0.005) * 0.15;

    switch (fx) {
      case 'heart': {
        [[880, 300, 20, 0], [930, 250, 15, 1.1], [856, 246, 12, 2.2]].forEach(([x, y, r, ph]) => {
          const fy = y - ((t * 0.03 + ph * 60) % 90);
          ctx.globalAlpha = 0.55 + 0.45 * Math.sin(t * 0.004 + ph);
          heart(ctx, x, fy, r * pulse, 'rgba(255,120,160,0.95)');
        });
        ctx.globalAlpha = 1;
        break;
      }
      case 'anger': {
        const x = 872, y = 262, s = 15 * pulse;
        ctx.strokeStyle = 'rgba(238,72,96,0.95)';
        ctx.lineWidth = 5.5;
        ctx.lineCap = 'round';
        for (let i = 0; i < 4; i++) {
          const a = (Math.PI / 2) * i + Math.PI / 4 + Math.sin(t * 0.006) * 0.06;
          ctx.beginPath();
          ctx.arc(x + Math.cos(a) * s * 1.5, y + Math.sin(a) * s * 1.5, s, a + 2.0, a + 4.3);
          ctx.stroke();
        }
        break;
      }
      case 'excl': {
        const x = 878, y = 258;
        ctx.fillStyle = 'rgba(255,214,90,0.96)';
        ctx.beginPath();
        ctx.moveTo(x, y - 26 * pulse);
        ctx.lineTo(x + 9, y - 2);
        ctx.lineTo(x - 9, y - 2);
        ctx.closePath();
        ctx.fill();
        ctx.beginPath();
        ctx.arc(x, y + 9, 6, 0, Math.PI * 2);
        ctx.fill();
        break;
      }
      case 'question': {
        ctx.fillStyle = 'rgba(150,190,255,0.95)';
        ctx.font = 'bold 58px system-ui,sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('?', 884, 300 + Math.sin(t * 0.004) * 6);
        break;
      }
      case 'zzz': {
        ctx.fillStyle = 'rgba(170,200,255,0.9)';
        ctx.textAlign = 'center';
        for (let i = 0; i < 3; i++) {
          const p = ((t * 0.00042 + i * 0.33) % 1);
          ctx.globalAlpha = 0.9 * (1 - p);
          ctx.font = 'bold ' + (22 + p * 22) + 'px system-ui,sans-serif';
          ctx.fillText('Z', 866 + p * 40, 300 - p * 90);
        }
        ctx.globalAlpha = 1;
        break;
      }
      case 'tear': {
        ctx.fillStyle = 'rgba(150,205,245,0.9)';
        [[536, 442], [716, 442]].forEach(([x, y], i) => {
          const p = (t * 0.0006 + i * 0.4) % 1;
          ctx.globalAlpha = 0.85 * (1 - p);
          ctx.beginPath();
          ctx.ellipse(x, y + p * 40, 5, 7, 0, 0, Math.PI * 2);
          ctx.fill();
        });
        ctx.globalAlpha = 1;
        break;
      }
      case 'sweat': {
        ctx.fillStyle = 'rgba(150,205,245,0.92)';
        const y = 250 + Math.sin(t * 0.003) * 5;
        ctx.beginPath();
        ctx.moveTo(884, y - 22);
        ctx.quadraticCurveTo(902, y + 4, 884, y + 12);
        ctx.quadraticCurveTo(866, y + 4, 884, y - 22);
        ctx.fill();
        break;
      }
      case 'star': {
        [[872, 268, 16, 0], [922, 300, 11, 0.7], [846, 316, 9, 1.5]].forEach(([x, y, r, ph]) => {
          ctx.globalAlpha = 0.5 + 0.5 * Math.sin(t * 0.005 + ph);
          star(ctx, x, y, r * pulse, 'rgba(255,232,140,0.95)');
        });
        ctx.globalAlpha = 1;
        break;
      }
      case 'rice': {
        const x = 876, y = 300;
        ctx.fillStyle = 'rgba(255,255,255,0.96)';
        ctx.beginPath();
        ctx.ellipse(x, y, 24, 15, 0, Math.PI, 0);
        ctx.fill();
        ctx.strokeStyle = 'rgba(120,140,180,0.8)';
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        ctx.arc(x, y, 24, Math.PI, 0);
        ctx.stroke();
        ctx.fillStyle = 'rgba(120,140,180,0.6)';
        for (let i = 0; i < 7; i++) {
          ctx.beginPath();
          ctx.ellipse(x - 16 + i * 5.4, y - 3 - (i % 2) * 3, 2.2, 1.4, 0.4, 0, Math.PI * 2);
          ctx.fill();
        }
        break;
      }
    }
    ctx.restore();
  }

  function heart(ctx, x, y, r, color) {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(x, y + r * 0.85);
    ctx.bezierCurveTo(x - r * 1.5, y - r * 0.35, x - r * 0.55, y - r * 1.25, x, y - r * 0.35);
    ctx.bezierCurveTo(x + r * 0.55, y - r * 1.25, x + r * 1.5, y - r * 0.35, x, y + r * 0.85);
    ctx.fill();
  }

  function star(ctx, x, y, r, color) {
    ctx.fillStyle = color;
    ctx.beginPath();
    for (let i = 0; i < 8; i++) {
      const a = (Math.PI / 4) * i - Math.PI / 2;
      const rr = i % 2 ? r * 0.38 : r;
      const px = x + Math.cos(a) * rr, py = y + Math.sin(a) * rr;
      i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
    }
    ctx.closePath();
    ctx.fill();
  }

  global.Rig = { load, draw, EMOTION, ORDER, MISSING };
})(window);
