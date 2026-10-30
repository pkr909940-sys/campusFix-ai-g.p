(() => {
  const escapeHtml = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const barList = (items, labelKey, countKey) => {
    if (!items.length) return '<p class="muted">No data yet.</p>';
    const max = Math.max(...items.map(x => Number(x[countKey]) || 0), 1);
    return items.map(x => `<div class="bar-item"><div class="bar-label"><span>${escapeHtml(x[labelKey])}</span><b>${Number(x[countKey])}</b></div><div class="bar-track"><i style="width:${Math.max(3, Number(x[countKey])/max*100)}%"></i></div></div>`).join('');
  };
  async function refresh() {
    const message = document.getElementById('statsMessage'); if (message) message.textContent = 'Refreshing…';
    try {
      const response = await fetch('/api/stats', {headers:{'Accept':'application/json'}});
      if (!response.ok) throw new Error('Could not load analytics');
      const data = await response.json();
      document.getElementById('categoryBars').innerHTML = barList(data.categories, 'name', 'count');
      document.getElementById('priorityBars').innerHTML = barList(Object.entries(data.priorities).map(([name,count])=>({name,count})), 'name', 'count');
      document.getElementById('locationBars').innerHTML = barList(data.locations, 'name', 'count');
      if (message) message.textContent = `Updated · ${data.total} reports`;
    } catch (e) { if (message) message.textContent = 'Analytics unavailable. Refresh the page and sign in again.'; }
  }
  document.getElementById('refreshStats')?.addEventListener('click', refresh);
  refresh();
})();
