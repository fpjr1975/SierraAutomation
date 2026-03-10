function toggleHelp() {
  const c = document.getElementById('helpContent');
  const a = document.getElementById('helpArrow');
  if (!c || !a) return;
  if (c.style.display === 'none' || c.style.display === '') {
    c.style.display = 'block';
    a.textContent = '▲';
    localStorage.setItem('help_open_' + location.pathname, '1');
  } else {
    c.style.display = 'none';
    a.textContent = '▼';
    localStorage.setItem('help_open_' + location.pathname, '0');
  }
}
// Restaurar estado salvo
document.addEventListener('DOMContentLoaded', function() {
  if (localStorage.getItem('help_open_' + location.pathname) === '1') {
    var c = document.getElementById('helpContent');
    var a = document.getElementById('helpArrow');
    if (c) c.style.display = 'block';
    if (a) a.textContent = '▲';
  }
});
