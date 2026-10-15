(function () {
  var menu = document.getElementById('menu'), scrim = document.getElementById('scrim');
  function toggle(open) { document.body.classList.toggle('nav-open', open); }
  if (menu) menu.addEventListener('click', function () { toggle(!document.body.classList.contains('nav-open')); });
  if (scrim) scrim.addEventListener('click', function () { toggle(false); });

  // Delete confirmation: the button unlocks only when the project id is typed exactly.
  var confirmInput = document.getElementById('confirm'), delBtn = document.getElementById('delbtn');
  if (confirmInput && delBtn) {
    confirmInput.addEventListener('input', function () {
      delBtn.disabled = confirmInput.value.trim() !== confirmInput.dataset.slug;
    });
  }

  // Suggest build/start commands for the chosen runtime (only fills empty fields).
  var rt = document.getElementById('runtime');
  if (rt) {
    var defaults = JSON.parse(rt.dataset.defaults || '{}');
    rt.addEventListener('change', function () {
      var d = defaults[rt.value] || ['', ''];
      var b = document.querySelector('[name=build_command]'), s = document.querySelector('[name=start_command]');
      if (b && !b.dataset.touched) b.value = d[0];
      if (s && !s.dataset.touched) s.value = d[1];
    });
    ['build_command', 'start_command'].forEach(function (n) {
      var el = document.querySelector('[name=' + n + ']');
      if (el) el.addEventListener('input', function () { el.dataset.touched = '1'; });
    });
  }
})();

// Live server metrics. Values come only from /api/metrics (real psutil readings); on failure the panel shows "unavailable".
(function () {
  var box = document.getElementById('live');
  if (!box) return;
  var state = document.getElementById('live-state'), last = null;
  function $(sel) { return box.querySelector(sel); }
  function set(k, v) { var el = $('[data-m="' + k + '"]'); if (el) el.textContent = v; }
  function bar(k, v) { var el = $('[data-p="' + k + '"]'); if (el) el.value = v; }
  function bytes(n) { var u = ['B', 'KB', 'MB', 'GB', 'TB'], i = 0; while (n >= 1024 && i < 4) { n /= 1024; i++; } return n.toFixed(i ? 1 : 0) + ' ' + u[i]; }
  function dur(s) { var d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60); return (d ? d + 'd ' : '') + h + 'h ' + m + 'm'; }
  function clear() { ['cpu', 'ram', 'disk', 'net_down', 'load', 'uptime'].forEach(function (k) { set(k, '—'); }); ['ram_detail', 'disk_detail', 'net_up', 'procs'].forEach(function (k) { set(k, ''); }); ['cpu', 'ram', 'disk'].forEach(function (k) { bar(k, 0); }); }
  function tick() {
    fetch(box.dataset.endpoint, { credentials: 'same-origin', cache: 'no-store' })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (m) {
        state.textContent = box.dataset.up;
        set('cpu', m.cpu.toFixed(0) + '%'); bar('cpu', m.cpu);
        set('ram', m.ram.pct.toFixed(0) + '%'); bar('ram', m.ram.pct); set('ram_detail', bytes(m.ram.used) + ' / ' + bytes(m.ram.total));
        set('disk', m.disk.pct.toFixed(0) + '%'); bar('disk', m.disk.pct); set('disk_detail', bytes(m.disk.used) + ' / ' + bytes(m.disk.total));
        if (last) {
          var dt = m.ts - last.ts;
          if (dt > 0) { set('net_down', '↓ ' + bytes((m.net.recv - last.net.recv) / dt) + '/s'); set('net_up', '↑ ' + bytes((m.net.sent - last.net.sent) / dt) + '/s'); }
        } else { set('net_down', '…'); }
        last = m;
        set('load', m.load ? m.load.map(function (x) { return x.toFixed(2); }).join(' ') : '—');
        set('procs', m.processes + ' proc');
        set('uptime', dur(m.uptime_s));
      })
      .catch(function () { state.textContent = box.dataset.down; last = null; clear(); });
  }
  tick(); setInterval(tick, 5000);
})();
