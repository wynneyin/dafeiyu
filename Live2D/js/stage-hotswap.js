/* 舞台热切换：角色管理页换皮套后，舞台自动刷新。
 *
 * 管理页写 Live2D/avatar.json（token 每次换皮套递增），
 * 这里轮询 token，变化就 location.reload()。
 * 入口 HTML 和 model_name.js 由 Live2D 静态服务器加 no-store，
 * 所以 reload 一定能拿到新模型名。
 */
(() => {
  if (!document.getElementById('stage')) return;

  const url = './avatar.json';
  let last = null;

  async function poll() {
    try {
      const res = await fetch(url + '?_=' + Date.now(), {
        cache: 'no-store',
        signal: AbortSignal.timeout(1500),
      });
      if (!res.ok) throw new Error('avatar state unavailable');
      const data = await res.json();
      const token = String(data.token == null ? '' : data.token);
      if (last === null) {
        last = token;                 // 初次加载只记住，不刷新
      } else if (token && token !== last) {
        location.reload();
        return;
      }
    } catch {
      /* 管理页没启动/没写过 avatar.json 时静默跳过 */
    }
    setTimeout(poll, 1800);
  }

  poll();
})();
