// Admin menu visibility — include in all pages
(function(){
    const token = localStorage.getItem('sierra_token');
    if(!token) return;
    fetch('/api/auth/me', {headers:{'Authorization':'Bearer '+token}})
    .then(r=>r.json()).then(u=>{
        // Update username in sidebar (different pages use different IDs)
        ['userName','sideUser'].forEach(id=>{
            const el = document.getElementById(id);
            if(el && (!el.textContent || el.textContent === '—')) el.textContent = u.nome || u.email || '—';
        });
        if(u.role === 'admin'){
            const s = document.getElementById('adminSection'); if(s) s.style.display='';
            const g = document.getElementById('gestorLink'); if(g) g.style.display='';
        }
    }).catch(()=>{});
})();
