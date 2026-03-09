"""
Páginas HTML da aplicação.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["pages"])


@router.get("/cotacao", response_class=HTMLResponse)
async def cotacao_page():
    return """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Sierra — Nova Cotação</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #0f1923;
                color: #e0e0e0;
                min-height: 100vh;
            }
            .navbar {
                background: rgba(255,255,255,0.05);
                border-bottom: 1px solid rgba(255,255,255,0.08);
                padding: 15px 30px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .navbar h1 { font-size: 20px; color: #fff; cursor: pointer; }
            .navbar .nav-links { display: flex; gap: 20px; align-items: center; }
            .navbar .nav-links a {
                color: #8892b0; text-decoration: none; font-size: 14px;
                transition: color 0.2s;
            }
            .navbar .nav-links a:hover, .navbar .nav-links a.active { color: #4fc3f7; }
            .navbar .btn-logout {
                background: rgba(239,83,80,0.2); color: #ef5350;
                border: 1px solid rgba(239,83,80,0.3);
                padding: 8px 16px; border-radius: 8px; cursor: pointer; font-size: 13px;
            }
            .container { max-width: 900px; margin: 30px auto; padding: 0 20px; }
            h2 { font-size: 24px; margin-bottom: 24px; color: #fff; }

            /* Steps */
            .steps {
                display: flex; gap: 0; margin-bottom: 30px;
                background: rgba(255,255,255,0.03);
                border-radius: 12px; overflow: hidden;
                border: 1px solid rgba(255,255,255,0.06);
            }
            .step {
                flex: 1; padding: 16px; text-align: center;
                font-size: 14px; color: #8892b0;
                border-right: 1px solid rgba(255,255,255,0.06);
                transition: all 0.3s;
            }
            .step:last-child { border-right: none; }
            .step.active { background: rgba(79,195,247,0.1); color: #4fc3f7; font-weight: 600; }
            .step.done { background: rgba(102,187,106,0.1); color: #66bb6a; }
            .step .step-num {
                display: inline-block; width: 28px; height: 28px; line-height: 28px;
                border-radius: 50%; background: rgba(255,255,255,0.1);
                margin-bottom: 6px; font-weight: 700;
            }
            .step.active .step-num { background: rgba(79,195,247,0.3); }
            .step.done .step-num { background: rgba(102,187,106,0.3); }

            /* Upload area */
            .upload-area {
                border: 2px dashed rgba(255,255,255,0.15);
                border-radius: 16px;
                padding: 40px;
                text-align: center;
                cursor: pointer;
                transition: all 0.3s;
                margin-bottom: 20px;
                background: rgba(255,255,255,0.02);
            }
            .upload-area:hover {
                border-color: #4fc3f7;
                background: rgba(79,195,247,0.05);
            }
            .upload-area.dragging {
                border-color: #4fc3f7;
                background: rgba(79,195,247,0.1);
            }
            .upload-area .icon { font-size: 48px; margin-bottom: 12px; }
            .upload-area p { color: #8892b0; font-size: 14px; }
            .upload-area input[type="file"] { display: none; }

            /* Form */
            .form-row { display: flex; gap: 16px; margin-bottom: 20px; }
            .form-group { flex: 1; }
            .form-group label {
                display: block; font-size: 13px; color: #8892b0;
                margin-bottom: 6px; font-weight: 500;
            }
            .form-group input, .form-group select {
                width: 100%; padding: 12px 16px;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 10px;
                background: rgba(255,255,255,0.05);
                color: #fff; font-size: 15px; outline: none;
            }
            .form-group input:focus { border-color: #4fc3f7; }

            /* Cards de dados extraídos */
            .data-card {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 16px;
            }
            .data-card h3 {
                font-size: 15px; color: #4fc3f7; margin-bottom: 12px;
                display: flex; align-items: center; gap: 8px;
            }
            .data-card .field {
                display: flex; justify-content: space-between;
                padding: 6px 0;
                border-bottom: 1px solid rgba(255,255,255,0.04);
                font-size: 14px;
            }
            .data-card .field:last-child { border-bottom: none; }
            .data-card .field .label { color: #8892b0; }
            .data-card .field .value { color: #fff; font-weight: 500; }

            /* Buttons */
            .btn {
                padding: 14px 28px; border: none; border-radius: 10px;
                font-size: 16px; font-weight: 600; cursor: pointer;
                transition: all 0.2s; display: inline-flex;
                align-items: center; gap: 8px;
            }
            .btn-primary {
                background: linear-gradient(135deg, #4fc3f7, #0288d1);
                color: #fff;
            }
            .btn-primary:hover { transform: translateY(-2px); box-shadow: 0 10px 25px rgba(79,195,247,0.3); }
            .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
            .btn-secondary {
                background: rgba(255,255,255,0.08); color: #8892b0;
                border: 1px solid rgba(255,255,255,0.1);
            }
            .btn-back { position: absolute; left: 20px; }

            /* Results */
            .result-card {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 12px;
                display: flex; justify-content: space-between; align-items: center;
                transition: all 0.2s;
            }
            .result-card:hover { border-color: rgba(79,195,247,0.3); }
            .result-card .seg-name { font-size: 16px; font-weight: 600; color: #fff; }
            .result-card .seg-quote { font-size: 12px; color: #8892b0; }
            .result-card .premio {
                font-size: 22px; font-weight: 700; color: #66bb6a;
            }
            .result-card .franquia { font-size: 13px; color: #8892b0; }
            .result-card.error { opacity: 0.5; }
            .result-card.error .premio { color: #ef5350; font-size: 14px; }

            /* Loading */
            .loading-spinner {
                text-align: center; padding: 60px;
            }
            .loading-spinner .spinner {
                width: 50px; height: 50px;
                border: 4px solid rgba(255,255,255,0.1);
                border-top: 4px solid #4fc3f7;
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin: 0 auto 20px;
            }
            @keyframes spin { to { transform: rotate(360deg); } }

            .alert {
                padding: 14px 20px;
                border-radius: 10px;
                margin-bottom: 16px;
                font-size: 14px;
            }
            .alert-success { background: rgba(102,187,106,0.15); color: #66bb6a; border: 1px solid rgba(102,187,106,0.2); }
            .alert-error { background: rgba(239,83,80,0.15); color: #ef5350; border: 1px solid rgba(239,83,80,0.2); }
            .alert-info { background: rgba(79,195,247,0.15); color: #4fc3f7; border: 1px solid rgba(79,195,247,0.2); }

            .hidden { display: none !important; }
        </style>
    </head>
    <body>
        <div class="navbar">
            <h1 onclick="window.location='/dashboard'">🏔️ Sierra</h1>
            <div class="nav-links">
                <a href="/dashboard">Dashboard</a>
                <a href="/cotacao" class="active">Nova Cotação</a>
                <a href="/cotacoes">Histórico</a>
            </div>
            <button class="btn-logout" onclick="logout()">Sair</button>
        </div>

        <div class="container">
            <h2>🚗 Nova Cotação</h2>

            <!-- Steps -->
            <div class="steps">
                <div class="step active" id="step1-indicator">
                    <div class="step-num">1</div><br>Documentos
                </div>
                <div class="step" id="step2-indicator">
                    <div class="step-num">2</div><br>Conferir Dados
                </div>
                <div class="step" id="step3-indicator">
                    <div class="step-num">3</div><br>Resultados
                </div>
            </div>

            <!-- Step 1: Upload -->
            <div id="step1">
                <div class="upload-area" id="cnhArea" onclick="document.getElementById('cnhInput').click()"
                     ondragover="event.preventDefault(); this.classList.add('dragging')"
                     ondragleave="this.classList.remove('dragging')"
                     ondrop="handleDrop(event, 'cnh')">
                    <div class="icon" id="cnhIcon">📋</div>
                    <p id="cnhLabel"><strong>CNH</strong> — Arraste ou clique para enviar</p>
                    <p style="font-size:12px; margin-top:8px">Foto (qualquer ângulo) ou PDF</p>
                    <input type="file" id="cnhInput" accept="image/*,.pdf" onchange="uploadDoc('cnh', this.files[0])">
                </div>

                <div class="upload-area" id="crvlArea" onclick="document.getElementById('crvlInput').click()"
                     ondragover="event.preventDefault(); this.classList.add('dragging')"
                     ondragleave="this.classList.remove('dragging')"
                     ondrop="handleDrop(event, 'crvl')">
                    <div class="icon" id="crvlIcon">🚗</div>
                    <p id="crvlLabel"><strong>CRVL</strong> — Arraste ou clique para enviar</p>
                    <p style="font-size:12px; margin-top:8px">Foto (qualquer ângulo) ou PDF</p>
                    <input type="file" id="crvlInput" accept="image/*,.pdf" onchange="uploadDoc('crvl', this.files[0])">
                </div>

                <div class="form-row">
                    <div class="form-group">
                        <label>CEP de Pernoite (onde o carro dorme)</label>
                        <input type="text" id="cepInput" placeholder="95084-270" maxlength="10"
                               onkeydown="if(event.key==='Enter') sendCep()">
                    </div>
                    <div class="form-group" style="flex:0 0 auto; display:flex; align-items:flex-end;">
                        <button class="btn btn-secondary" onclick="sendCep()">Confirmar CEP</button>
                    </div>
                </div>
                <div id="cepInfo" class="hidden"></div>
                <div id="step1Alerts"></div>
            </div>

            <!-- Step 2: Conferir dados -->
            <div id="step2" class="hidden">
                <div id="dadosExtraidos"></div>
                <div style="display:flex; gap:12px; margin-top:24px;">
                    <button class="btn btn-secondary" onclick="goToStep(1)">← Voltar</button>
                    <button class="btn btn-primary" id="btnCalcular" onclick="calcular()">
                        🚀 Calcular no Agilizador
                    </button>
                </div>
            </div>

            <!-- Step 3: Resultados -->
            <div id="step3" class="hidden">
                <div id="resultadosArea"></div>
                <div style="margin-top:24px; display:flex; gap:12px;">
                    <button class="btn btn-primary" onclick="novaCotacao()">+ Nova Cotação</button>
                    <button class="btn btn-secondary" onclick="window.location='/cotacoes'">Ver Histórico</button>
                </div>
            </div>
        </div>

        <script>
            const token = localStorage.getItem('sierra_token');
            if (!token) window.location.href = '/';
            const headers = { 'Authorization': `Bearer ${token}` };

            let currentStep = 1;
            let sessionData = { cnh: null, crvl: null, cep: null, endereco: null };

            // Inicia sessão
            async function initSession() {
                const resp = await fetch('/api/cotacoes/nova', { method: 'POST', headers });
                if (resp.status === 401) { logout(); return; }
                const data = await resp.json();
                console.log('Sessão iniciada:', data);
            }
            initSession();

            function handleDrop(e, type) {
                e.preventDefault();
                e.currentTarget.classList.remove('dragging');
                const file = e.dataTransfer.files[0];
                if (file) uploadDoc(type, file);
            }

            async function uploadDoc(type, file) {
                if (!file) return;
                const area = document.getElementById(type + 'Area');
                const icon = document.getElementById(type + 'Icon');
                const label = document.getElementById(type + 'Label');

                icon.textContent = '⏳';
                label.innerHTML = `<strong>Processando ${type.toUpperCase()}...</strong>`;

                const formData = new FormData();
                formData.append('file', file);

                try {
                    const resp = await fetch(`/api/cotacoes/upload-${type}`, {
                        method: 'POST',
                        headers: { 'Authorization': `Bearer ${token}` },
                        body: formData
                    });
                    const data = await resp.json();

                    if (resp.ok) {
                        icon.textContent = '✅';
                        const docData = data[type];
                        if (type === 'cnh') {
                            label.innerHTML = `<strong>${docData.nome}</strong><br>CPF: ${docData.cpf || 'N/D'}`;
                            sessionData.cnh = docData;
                        } else {
                            label.innerHTML = `<strong>${docData.placa}</strong> — ${docData.modelo || 'N/D'}`;
                            sessionData.crvl = docData;
                        }
                        area.style.borderColor = 'rgba(102,187,106,0.5)';
                        checkReady();
                    } else {
                        icon.textContent = '❌';
                        label.innerHTML = `<strong>Erro:</strong> ${data.detail || 'Falha no OCR'}`;
                        area.style.borderColor = 'rgba(239,83,80,0.5)';
                    }
                } catch(err) {
                    icon.textContent = '❌';
                    label.innerHTML = '<strong>Erro de conexão</strong>';
                }
            }

            async function sendCep() {
                const cep = document.getElementById('cepInput').value.trim();
                if (!cep) return;

                const formData = new FormData();
                formData.append('cep', cep);

                try {
                    const resp = await fetch('/api/cotacoes/cep', {
                        method: 'POST',
                        headers: { 'Authorization': `Bearer ${token}` },
                        body: formData
                    });
                    const data = await resp.json();

                    const info = document.getElementById('cepInfo');
                    if (resp.ok) {
                        info.className = 'alert alert-success';
                        info.textContent = `✅ ${data.cep} — ${data.endereco || 'Endereço encontrado'}`;
                        sessionData.cep = data.cep;
                        sessionData.endereco = data.endereco;
                        checkReady();
                    } else {
                        info.className = 'alert alert-error';
                        info.textContent = `❌ ${data.detail}`;
                    }
                } catch(err) {
                    document.getElementById('cepInfo').className = 'alert alert-error';
                    document.getElementById('cepInfo').textContent = 'Erro de conexão';
                }
            }

            function checkReady() {
                if (sessionData.cnh && sessionData.crvl && sessionData.cep) {
                    setTimeout(() => goToStep(2), 500);
                }
            }

            function goToStep(step) {
                currentStep = step;
                document.getElementById('step1').classList.toggle('hidden', step !== 1);
                document.getElementById('step2').classList.toggle('hidden', step !== 2);
                document.getElementById('step3').classList.toggle('hidden', step !== 3);

                for (let i = 1; i <= 3; i++) {
                    const el = document.getElementById(`step${i}-indicator`);
                    el.classList.remove('active', 'done');
                    if (i < step) el.classList.add('done');
                    if (i === step) el.classList.add('active');
                }

                if (step === 2) renderDados();
            }

            function renderDados() {
                const c = sessionData.cnh;
                const v = sessionData.crvl;
                let html = '';

                html += `<div class="data-card"><h3>👤 Segurado</h3>`;
                html += field('Nome', c.nome);
                html += field('CPF', c.cpf);
                html += field('Nascimento', c.nascimento);
                html += field('CNH', c.numero_cnh || c.registro);
                html += `</div>`;

                html += `<div class="data-card"><h3>🚗 Veículo</h3>`;
                html += field('Placa', v.placa);
                html += field('Modelo', v.modelo);
                html += field('Ano', `${v.ano_fabricacao || '?'}/${v.ano_modelo || '?'}`);
                html += field('Cor', v.cor);
                html += field('Combustível', v.combustivel);
                html += field('Chassi', v.chassi);
                html += `</div>`;

                html += `<div class="data-card"><h3>🌙 Pernoite</h3>`;
                html += field('CEP', sessionData.cep);
                html += field('Endereço', sessionData.endereco || 'N/D');
                html += `</div>`;

                document.getElementById('dadosExtraidos').innerHTML = html;
            }

            function field(label, value) {
                return `<div class="field"><span class="label">${label}</span><span class="value">${value || 'N/D'}</span></div>`;
            }

            async function calcular() {
                const btn = document.getElementById('btnCalcular');
                btn.disabled = true;
                btn.textContent = '⏳ Calculando...';
                goToStep(3);

                document.getElementById('resultadosArea').innerHTML = `
                    <div class="loading-spinner">
                        <div class="spinner"></div>
                        <p>Calculando cotações no Agilizador...</p>
                        <p style="font-size:13px; color:#8892b0; margin-top:8px">Isso leva cerca de 30-60 segundos</p>
                    </div>`;

                try {
                    const resp = await fetch('/api/cotacoes/calcular', { method: 'POST', headers });
                    if (!resp.ok) {
                        const data = await resp.json();
                        showError(data.detail || 'Erro ao calcular');
                        return;
                    }
                    // Poll status
                    pollResults();
                } catch(err) {
                    showError('Erro de conexão');
                }
            }

            async function pollResults() {
                let attempts = 0;
                const maxAttempts = 30; // 30 x 3s = 90s

                const interval = setInterval(async () => {
                    attempts++;
                    try {
                        const resp = await fetch('/api/cotacoes/status', { headers });
                        const data = await resp.json();

                        if (data.status === 'done') {
                            clearInterval(interval);
                            renderResultados(data.resultados);
                        } else if (data.status === 'error') {
                            clearInterval(interval);
                            showError(data.erro || 'Erro no cálculo');
                        } else if (attempts >= maxAttempts) {
                            clearInterval(interval);
                            showError('Tempo esgotado — tente novamente');
                        }
                    } catch(e) {
                        clearInterval(interval);
                        showError('Erro de conexão');
                    }
                }, 3000);
            }

            function renderResultados(resultados) {
                if (!resultados || resultados.length === 0) {
                    document.getElementById('resultadosArea').innerHTML = `
                        <div class="alert alert-info">Nenhum resultado retornado. Tente novamente.</div>`;
                    return;
                }

                // Separa com valor e sem
                const comValor = resultados.filter(r => r.premio);
                const semValor = resultados.filter(r => !r.premio);

                let html = `<div class="alert alert-success">✅ ${resultados.length} resultados encontrados</div>`;

                comValor.forEach(r => {
                    html += `
                    <div class="result-card">
                        <div>
                            <div class="seg-name">${r.seguradora || 'N/D'}</div>
                            <div class="seg-quote">${r.numero ? 'Cotação #' + r.numero : ''} ${r.parcelas || ''}</div>
                        </div>
                        <div style="text-align:right">
                            <div class="premio">R$ ${r.premio}</div>
                            <div class="franquia">Franquia: R$ ${r.franquia || 'N/D'}</div>
                        </div>
                    </div>`;
                });

                if (semValor.length > 0) {
                    html += `<h3 style="margin: 20px 0 12px; color: #8892b0; font-size: 14px;">⚠️ Sem resultado</h3>`;
                    semValor.forEach(r => {
                        html += `
                        <div class="result-card error">
                            <div>
                                <div class="seg-name">${r.seguradora || 'N/D'}</div>
                            </div>
                            <div style="text-align:right">
                                <div class="premio">${r.mensagem || 'Sem cotação'}</div>
                            </div>
                        </div>`;
                    });
                }

                document.getElementById('resultadosArea').innerHTML = html;
            }

            function showError(msg) {
                document.getElementById('resultadosArea').innerHTML = `
                    <div class="alert alert-error">❌ ${msg}</div>
                    <button class="btn btn-primary" onclick="novaCotacao()" style="margin-top:16px">Tentar novamente</button>`;
            }

            function novaCotacao() {
                sessionData = { cnh: null, crvl: null, cep: null, endereco: null };
                // Reset upload areas
                ['cnh', 'crvl'].forEach(type => {
                    document.getElementById(type + 'Icon').textContent = type === 'cnh' ? '📋' : '🚗';
                    document.getElementById(type + 'Label').innerHTML = `<strong>${type.toUpperCase()}</strong> — Arraste ou clique para enviar`;
                    document.getElementById(type + 'Area').style.borderColor = '';
                    document.getElementById(type + 'Input').value = '';
                });
                document.getElementById('cepInput').value = '';
                document.getElementById('cepInfo').className = 'hidden';
                goToStep(1);
                initSession();
            }

            function logout() {
                localStorage.removeItem('sierra_token');
                localStorage.removeItem('sierra_user');
                window.location.href = '/';
            }
        </script>
    </body>
    </html>
    """


@router.get("/cotacoes", response_class=HTMLResponse)
async def cotacoes_page():
    import os
    html_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'cotacoes.html')
    with open(html_path, 'r') as f:
        return f.read()

@router.get("/cotacoes-historico", response_class=HTMLResponse)
async def cotacoes_historico_page():
    return """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Sierra — Histórico de Cotações</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #0f1923; color: #e0e0e0; min-height: 100vh;
            }
            .navbar {
                background: rgba(255,255,255,0.05);
                border-bottom: 1px solid rgba(255,255,255,0.08);
                padding: 15px 30px;
                display: flex; justify-content: space-between; align-items: center;
            }
            .navbar h1 { font-size: 20px; color: #fff; cursor: pointer; }
            .navbar .nav-links { display: flex; gap: 20px; align-items: center; }
            .navbar .nav-links a {
                color: #8892b0; text-decoration: none; font-size: 14px; transition: color 0.2s;
            }
            .navbar .nav-links a:hover, .navbar .nav-links a.active { color: #4fc3f7; }
            .navbar .btn-logout {
                background: rgba(239,83,80,0.2); color: #ef5350;
                border: 1px solid rgba(239,83,80,0.3);
                padding: 8px 16px; border-radius: 8px; cursor: pointer; font-size: 13px;
            }
            .container { max-width: 1000px; margin: 30px auto; padding: 0 20px; }
            h2 { font-size: 24px; margin-bottom: 24px; color: #fff; }
            .section {
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.06);
                border-radius: 16px; padding: 24px;
            }
            table { width: 100%; border-collapse: collapse; }
            th, td {
                padding: 12px; text-align: left;
                border-bottom: 1px solid rgba(255,255,255,0.06); font-size: 14px;
            }
            th { color: #8892b0; font-weight: 500; }
            .badge { padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 500; }
            .badge-ok { background: rgba(102,187,106,0.15); color: #66bb6a; }
            .badge-calc { background: rgba(79,195,247,0.15); color: #4fc3f7; }
            .btn-ver {
                background: rgba(79,195,247,0.15); color: #4fc3f7;
                border: 1px solid rgba(79,195,247,0.2);
                padding: 6px 14px; border-radius: 8px; cursor: pointer; font-size: 13px;
            }
            .loading { text-align: center; color: #8892b0; padding: 40px; }
        </style>
    </head>
    <body>
        <div class="navbar">
            <h1 onclick="window.location='/dashboard'">🏔️ Sierra</h1>
            <div class="nav-links">
                <a href="/dashboard">Dashboard</a>
                <a href="/cotacao">Nova Cotação</a>
                <a href="/cotacoes" class="active">Histórico</a>
            </div>
            <button class="btn-logout" onclick="logout()">Sair</button>
        </div>

        <div class="container">
            <h2>📋 Histórico de Cotações</h2>
            <div class="section">
                <div id="tableArea"><p class="loading">Carregando...</p></div>
            </div>
        </div>

        <script>
            const token = localStorage.getItem('sierra_token');
            if (!token) window.location.href = '/';
            const headers = { 'Authorization': `Bearer ${token}` };

            async function loadCotacoes() {
                try {
                    const resp = await fetch('/api/cotacoes/historico', { headers });
                    if (resp.status === 401) { logout(); return; }
                    const data = await resp.json();
                    if (data.cotacoes.length === 0) {
                        document.getElementById('tableArea').innerHTML = '<p class="loading">Nenhuma cotação registrada</p>';
                        return;
                    }
                    let html = '<table><thead><tr><th>#</th><th>Cliente</th><th>Veículo</th><th>Placa</th><th>Tipo</th><th>Status</th><th>Data</th><th></th></tr></thead><tbody>';
                    data.cotacoes.forEach(c => {
                        const dt = c.data ? new Date(c.data).toLocaleDateString('pt-BR') : '-';
                        const badge = c.status === 'calculada' ? 'badge-ok' : 'badge-calc';
                        html += `<tr>
                            <td>${c.id}</td>
                            <td>${c.cliente || 'N/D'}</td>
                            <td>${c.veiculo || 'N/D'}</td>
                            <td>${c.placa || 'N/D'}</td>
                            <td>${c.tipo}</td>
                            <td><span class="badge ${badge}">${c.status}</span></td>
                            <td>${dt}</td>
                            <td><button class="btn-ver" onclick="verResultados(${c.id})">Ver</button></td>
                        </tr>`;
                    });
                    html += '</tbody></table>';
                    html += `<p style="margin-top:16px; color:#8892b0; font-size:13px">${data.total} cotações no total</p>`;
                    document.getElementById('tableArea').innerHTML = html;
                } catch(e) { console.error(e); }
            }

            async function verResultados(id) {
                try {
                    const resp = await fetch(`/api/cotacoes/${id}/resultados`, { headers });
                    const data = await resp.json();
                    if (!data.resultados || data.resultados.length === 0) {
                        alert('Nenhum resultado para esta cotação');
                        return;
                    }
                    let html = `<h3 style="color:#fff;margin-bottom:16px">📊 Cotação #${id} — ${data.resultados.length} resultados</h3>`;
                    const comValor = data.resultados.filter(r => r.premio);
                    const semValor = data.resultados.filter(r => !r.premio);
                    comValor.forEach(r => {
                        html += `<div style="display:flex;justify-content:space-between;align-items:center;padding:12px;margin-bottom:8px;background:rgba(255,255,255,0.05);border-radius:10px;border:1px solid rgba(255,255,255,0.08)">
                            <div><strong style="color:#fff">${r.seguradora}</strong><br><span style="font-size:12px;color:#8892b0">${r.numero ? '#'+r.numero : ''} ${r.parcelas || ''}</span></div>
                            <div style="text-align:right"><span style="font-size:20px;font-weight:700;color:#66bb6a">R$ ${r.premio.toFixed(2)}</span><br><span style="font-size:12px;color:#8892b0">Franquia: R$ ${(r.franquia||0).toFixed(2)}</span></div>
                        </div>`;
                    });
                    if (semValor.length > 0) {
                        html += `<p style="margin:12px 0 8px;color:#8892b0;font-size:13px">⚠️ Sem resultado:</p>`;
                        semValor.forEach(r => {
                            html += `<div style="padding:8px 12px;margin-bottom:4px;background:rgba(255,255,255,0.02);border-radius:8px;font-size:13px;color:#8892b0">${r.seguradora}: ${r.mensagem || 'Sem cotação'}</div>`;
                        });
                    }
                    html += `<div style="margin-top:16px;text-align:right"><button onclick="closeResultModal()" style="padding:10px 20px;border:1px solid rgba(255,255,255,0.15);border-radius:8px;background:rgba(255,255,255,0.05);color:#fff;cursor:pointer">Fechar</button></div>`;
                    
                    // Cria modal dinâmico
                    let modal = document.getElementById('resultModal');
                    if (!modal) {
                        modal = document.createElement('div');
                        modal.id = 'resultModal';
                        modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);display:flex;justify-content:center;align-items:center;z-index:1000';
                        modal.onclick = (e) => { if(e.target===modal) closeResultModal(); };
                        document.body.appendChild(modal);
                    }
                    modal.innerHTML = `<div style="background:#1a2332;border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:30px;width:90%;max-width:600px;max-height:85vh;overflow-y:auto">${html}</div>`;
                    modal.style.display = 'flex';
                } catch(e) { alert('Erro ao carregar resultados'); }
            }
            function closeResultModal() { const m = document.getElementById('resultModal'); if(m) m.style.display='none'; }

            function logout() {
                localStorage.removeItem('sierra_token');
                localStorage.removeItem('sierra_user');
                window.location.href = '/';
            }

            loadCotacoes();
        </script>
    </body>
    </html>
    """
