from flask import Flask, render_template_string, request, redirect, url_for
import requests
import json
import re
import pyautogui
from PIL import Image
import base64
import io
import time

# --- 1. CONFIGURAÇÃO DA IA ---
# ATENÇÃO: O LM Studio precisa estar rodando neste IP e porta, com o modelo carregado.
API_BASE_URL = "http://192.168.15.7:1234"
API_ENDPOINT = f"{API_BASE_URL}/v1/chat/completions"

# Modelo Padrão para Modo Texto (Chat Simples)
MODELO_TEXTO_PADRAO = "openai/gpt-oss-20b"
# CORRIGIDO: Nome exato para o modelo multimodal
MODELO_AGENTE_ESPECIFICO = "llava-llama-3-8b-v1_1"
# PROMPT CRÍTICO: Força o modelo a gerar APENAS o bloco de código
SYSTEM_PROMPT_AGENTE = (
    "Você é Luna, uma IA Agente Multimodal, capaz de analisar capturas de tela e interagir com o sistema operacional. "
    "Sua função é auxiliar o usuário na automação de tarefas na tela. "
    "SEMPRE responda em Português Brasileiro (pt-br). "
    "Você receberá uma captura de tela (Base64) e uma solicitação do usuário. "

    "INSTRUÇÃO CRÍTICA DE SAÍDA: "
    "Se você determinar que uma ação pode ser executada (ex: abrir programa, clicar em botão), **VOCÊ DEVE RESPONDER APENAS COM O CÓDIGO PYTHON** envolto em um bloco de código Markdown. "
    "**NÃO USE TEXTO EXPLICATIVO, INTRODUÇÕES OU CONCLUSÕES FORA DO BLOCO DE CÓDIGO.** "
    "O código DEVE começar e terminar exatamente com as tags de bloco de código."

    # 🚨 ADIÇÃO CRÍTICA: Priorizar comandos de teclado para estabilidade
    "**PRIORIZE SEMPRE** o uso de comandos de teclado (pyautogui.press, pyautogui.write, pyautogui.hotkey) e **EVITE** usar funções de localização visual como `pyautogui.locateOnScreen` ou `pyautogui.locateCenterOnScreen` para maior estabilidade, a menos que seja estritamente necessário."

    "Exemplo de SAÍDA PERFEITA: "
    "```python\n"
    "pyautogui.press('win')\n"
    "pyautogui.write('chrome')\n"
    "pyautogui.press('enter')\n"
    "time.sleep(2)\n"
    "pyautogui.write('youtube.com')\n"
    "pyautogui.press('enter')\n"
    "pyautogui.hotkey('alt', 'f4') # Comando de fechamento estável\n"
    "```. "
"### REGRA DE NAVEGAÇÃO WEB (CRÍTICA): "
"1. Se a tarefa envolver um navegador, **PRIORIZE SEMPRE** usar `pag.hotkey('ctrl', 'l')` (ou `pag.hotkey('alt', 'd')`) para focar na barra de endereço de um navegador já aberto ou no topo da tela. "
"2. **EVITE** usar `pag.press('super')` ou `pag.press('win')` para buscar programas. Use esses comandos apenas para tarefas que **exijam** a interação com o sistema operacional e não com um programa específico (ex: 'Abrir configurações'). "
"3. Para abrir um navegador se ele não estiver visível (último recurso), use o comando específico do SO (ex: Linux/GNOME: `pag.press('super'); pag.write('firefox'); pag.press('enter')`)."
# -----------------------------------------------------------
    "Se não puder agir, responda em Português com uma pergunta ou explicação curta."
)

# Prompt Padrão para Modo Texto (Chat simples)
SYSTEM_PROMPT_CHAT = (
    "Você é Luna, uma IA assistente inteligente e prestativa. "
    "SUA LINGUAGEM ÚNICA DE TRABALHO E RESPOSTA É O PORTUGUÊS BRASILEIRO (pt-br). "
    "NUNCA, em hipótese alguma, use inglês ou qualquer outro idioma em sua resposta final. "
    "Use Markdown para formatação (negrito, listas, blocos de código)."
)

app = Flask(__name__)


# --- FUNÇÕES DE AJUDA ---

def clean_response(text):
    """Limpa a resposta da IA de prefixos e metadados."""
    if not text:
        return ""

    # Remoção de metadados comuns em APIs de LLM
    text = re.sub(r'<\|channel\|>.*?final>?', '', text, flags=re.DOTALL).strip()
    text = re.sub(r'commentary to\s+\d+', '', text, flags=re.IGNORECASE).strip()

    # Remoção de saudações e números no início da resposta
    text = re.sub(
        r'^\s*[\w\d]*\s*(Olá|Oi|Como posso ajudar|o que posso fazer por você|Eu sou Luna|Fico feliz em ajudar)\s*[\?\!\.\:]*',
        r'\1', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'^\s*\d+\s*', '', text).strip()

    return text.lstrip()


@app.template_filter('nl2br')
def nl2br_filter(s):
    """Converte quebras de linha em tags <br> para HTML."""
    if not s: return ''
    return s.replace('\n', '<br>')


def take_screenshot_and_base64():
    """Tira uma captura de tela e codifica em base64 (PNG)."""
    try:
        screenshot = pyautogui.screenshot()

        # Redimensionamento (Opcional, mas reduz o payload para o LLM)
        MAX_SIZE = 1024
        width, height = screenshot.size
        if width > MAX_SIZE:
            height = int(MAX_SIZE * height / width)
            width = MAX_SIZE
        screenshot = screenshot.resize((width, height))

        buffered = io.BytesIO()
        screenshot.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()

        # Retorna o formato MIME type + base64 data
        return f"data:image/png;base64,{img_str}"
    except Exception as e:
        print(f"ERRO DE PERMISSÃO PYAUTOGUI: {e}")
        return None


def execute_agent_action(action_code):
    """Executa o código Python da IA (pyautogui) em um namespace seguro."""

    # 1. DESABILITA O FAIL-SAFE para evitar interrupções acidentais
    pyautogui.FAILSAFE = False

    # CORREÇÃO: Adiciona o alias 'pag' (PyAutoGUI) para caso a IA o utilize.
    allowed_globals = {'pyautogui': pyautogui, 'time': time, 'pag': pyautogui}

    try:
        # Importante: Sandboxing básico
        exec(action_code, {"__builtins__": None}, allowed_globals)

        # 2. Reabilita o Fail-Safe (Melhor prática)
        pyautogui.FAILSAFE = True

        return "Ação executada com sucesso! (Código Python rodado na máquina)."
    except Exception as e:
        # 3. Garante que o Fail-Safe seja reativado mesmo em caso de erro
        pyautogui.FAILSAFE = True
        return f"Erro na execução da ação (pyautogui): {e}"


# --- 2. TEMPLATE HTML/CSS/JS (Não alterado) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Luna IA</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&display=swap" rel="stylesheet">

    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-dark.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>

<style>
        /* --- VARIÁVEIS DE TEMA (DARK NEON) --- */
        :root {
            --bg-body: #1E1E1E;
            --bg-card: #252525;
            --bg-chat: #2A2A2A;
            --bg-input: #333333;
            --text-main: #E0E0E0;
            --text-dim: #A0A0A0;
            --accent-green: #00FFB2;
            --accent-red: #FF4444; 
            --border-color: #404040;
            --shadow: 0 8px 24px rgba(0,0,0, 0.4);
        }

        /* --- GLOBAL --- */
        body {
            background-color: var(--bg-body);
            color: var(--text-main);
            font-family: 'Inter', sans-serif;
            height: 100vh;
            overflow: hidden; /* Mantém o corpo sem rolagem */
            display: flex;
            flex-direction: column;
        }

        /* --- CUSTOM SCROLLBAR --- */
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: var(--bg-chat); }
        ::-webkit-scrollbar-thumb { background: #555; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #777; }

        /* --- LAYOUT --- */
        .main-wrapper {
            flex: 1;
            display: flex;
            justify-content: center;
            padding: 20px;
            max-width: 1200px;
            width: 100%;
            margin: 0 auto;
            /* 🔑 CORREÇÃO 1: Define explicitamente a altura para o Flexbox */
            height: calc(100vh - 40px);
        }

        .chat-card {
            background-color: var(--bg-card);
            width: 100%;
            height: 100%; /* Garante altura total no wrapper */
            border-radius: 16px;
            box-shadow: var(--shadow);
            border: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            position: relative;
        }

        /* --- HEADER --- */
        .chat-header {
            padding: 15px 20px;
            border-bottom: 1px solid var(--border-color);
            background: linear-gradient(180deg, rgba(40,40,40,1) 0%, rgba(37,37,37,1) 100%);
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-shrink: 0; /* Não permite que o header encolha */
        }
        .brand {
            display: flex;
            align-items: center;
            gap: 10px;
            font-weight: 600;
            font-size: 1.1rem;
            color: var(--accent-red); 
        }
        .brand-icon { font-size: 1.2rem; margin-top: -2px; }

        /* NOVO CSS: BOTÃO MODO AGENTE */
        #agentModeButton {
            background-color: var(--accent-green);
            color: var(--bg-card);
            border: none;
            padding: 5px 10px;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: background-color 0.2s;
        }
        #agentModeButton:hover {
            background-color: #00E6A0;
        }
        .agent-active {
            background-color: var(--accent-red) !important;
        }

        /* --- MESSAGES --- */
        .messages-area {
            flex: 1; /* Ocupa todo o espaço vertical restante */
            overflow-y: auto; /* Permite rolagem vertical */
            padding: 30px;
            background-color: var(--bg-chat);
            /* 🔑 CORREÇÃO 2: Garante que o item flexível possa encolher até 0 */
            min-height: 0;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        .msg-row { display: flex; width: 100%; }
        .msg-row.user { justify-content: flex-end; }
        .msg-row.ai { justify-content: flex-start; }

        .bubble {
            max-width: 85%;
            padding: 12px 18px;
            border-radius: 12px;
            line-height: 1.6;
            position: relative;
            font-size: 0.95rem;
            word-wrap: break-word;
        }

        .bubble.user {
            background-color: #383838;
            color: #fff;
            border-bottom-right-radius: 2px;
            border: 1px solid #444;
        }

        .bubble.ai {
            background-color: transparent;
            color: var(--text-main);
            padding-left: 0;
        }

        /* ESTILO PARA CÓDIGO MARKDOWN */
        .bubble.ai pre {
            background: #151515 !important;
            padding: 15px;
            border-radius: 8px;
            overflow-x: auto;
            border: 1px solid #444;
            margin-top: 10px;
            margin-bottom: 10px;
        }
        .bubble.ai code {
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 0.9rem;
        }
        .bubble.ai p { margin-bottom: 10px; }
        .bubble.ai p:last-child { margin-bottom: 0; }

        .ai-avatar {
            margin-right: 12px;
            font-size: 1.2rem;
            margin-top: 2px;
            flex-shrink: 0;
        }

        .ai-actions {
            margin-left: 10px;
            display: flex;
            align-items: flex-start; 
            gap: 5px;
            flex-shrink: 0;
        }
        .ai-actions .btn-action {
            padding: 5px;
            font-size: 0.9rem;
            opacity: 0.6;
            line-height: 1; 
        }
        .ai-actions .btn-action:hover {
            opacity: 1;
            color: var(--accent-green);
        }
        .ai-actions .btn-stop {
            color: var(--accent-red); 
        }

        /* --- INPUT --- */
        .input-area {
            background-color: var(--bg-card);
            padding: 20px;
            border-top: 1px solid var(--border-color);
            flex-shrink: 0; /* Não permite que a área de input encolha */
        }

        .input-container {
            background-color: var(--bg-input);
            border: 1px solid #444;
            border-radius: 24px;
            padding: 8px 15px;
            display: flex;
            align-items: flex-end;
            transition: border-color 0.2s;
        }

        .input-container:focus-within {
            border-color: var(--accent-green);
            box-shadow: 0 0 8px rgba(0, 255, 178, 0.1);
        }

        textarea {
            background: transparent;
            border: none;
            color: white;
            width: 100%;
            resize: none;
            padding: 10px 5px;
            font-family: 'Inter', sans-serif;
            max-height: 150px;
            outline: none;
        }
        textarea::placeholder { color: #666; }

        .btn-action {
            background: none;
            border: none;
            color: var(--text-dim);
            padding: 8px;
            cursor: pointer;
            transition: color 0.2s, transform 0.1s;
        }
        .btn-action:hover { color: var(--accent-green); }
        .btn-send { font-size: 1.2rem; color: var(--accent-green); }

        .recording { color: var(--accent-red) !important; animation: pulse 1.5s infinite; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }

        /* --- LOADING --- */
        .loading-overlay {
            display: none;
            margin-top: 10px;
            padding-left: 35px;
        }
        .typing-dots span {
            display: inline-block;
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background-color: var(--accent-green);
            margin-right: 3px;
            animation: typing 1.4s infinite ease-in-out both;
        }
        .typing-dots span:nth-child(1) { animation-delay: -0.32s; }
        span:nth-child(2) { animation-delay: -0.16s; }
        @keyframes typing { 0%, 80%, 100% { transform: scale(0); } 40% { transform: scale(1); } }

        .footer-info {
            text-align: center;
            font-size: 0.7rem;
            color: #555;
            margin-top: 8px;
        }

        /* CSS para exibir a captura de tela no modo agente */
        .screenshot-display {
            max-width: 100%;
            height: auto;
            border: 2px solid var(--accent-red);
            border-radius: 8px;
            margin-top: 10px;
        }
    </style>
</head>
<body>

    <div class="main-wrapper">
        <div class="chat-card">

            <div class="chat-header">
                <div class="brand">
                    <span class="brand-icon">&#x1F319;</span> Luna IA
                </div>
                <button id="agentModeButton" class="{% if agent_mode %}agent-active{% endif %}">
                    {% if agent_mode %}🛑 Modo AGENTE Ativo{% else %}✨ Modo AGENTE{% endif %}
                </button>
            </div>

            <div class="messages-area" id="messagesArea">

                {% if not previous_prompt and not error %}
                <div class="msg-row ai">
                    <div class="ai-avatar">&#x1F319;</div>
                    <div class="bubble ai markdown-content">
                        Olá! Eu sou a Luna. Fico feliz em ajudar. Clique em **Modo Agente** se precisar de automação de tela!
                    </div>
                </div>
                {% endif %}

                {% if agent_mode %}
                <div class="msg-row ai">
                    <div class="ai-avatar">🚨</div>
                    <div class="bubble ai" style="color: var(--accent-red);">
                        **MODO AGENTE ATIVO!** Modelo: **{{ MODELO_AGENTE_ESPECIFICO }}**. A Luna vai analisar sua tela e pode controlar seu mouse/teclado. Peça uma ação (ex: "Abra o Youtube").
                    </div>
                </div>
                {% endif %}

                {% if screenshot_b64 %}
                <div class="msg-row ai">
                    <div class="ai-avatar">🖼️</div>
                    <div class="bubble ai markdown-content">
                        **Captura de Tela Enviada para a Luna:**
                        <img src="{{ screenshot_b64 }}" class="screenshot-display" alt="Captura de Tela">
                    </div>
                </div>
                {% endif %}


                {% if previous_prompt %}
                <div class="msg-row user">
                    <div class="bubble user">
                        {{ previous_prompt | replace('\\n', '<br>') | safe }}
                    </div>
                </div>
                {% endif %}

                {% if response_text %}
                <div class="msg-row ai">
                    <div class="ai-avatar">&#x1F319;</div>
                    <div id="rawResponseData" style="display:none;">{{ response_text }}</div>
                    <div class="bubble ai markdown-content" id="aiResponse"></div>

                    <div class="ai-actions" id="aiActionsContainer">
                        <button type="button" class="btn-action btn-edit" id="editButton" title="Editar pedido anterior">✏️</button>
                        <button type="button" class="btn-action btn-stop" id="stopButton" title="Cancelar/Limpar">🛑</button>
                    </div>

                </div>
                {% endif %}

                {% if agent_action_result %}
                <div class="msg-row ai">
                    <div class="ai-avatar">✅</div>
                    <div class="bubble ai markdown-content" style="color: var(--accent-green);">
                        **Ação de Agente Concluída:** {{ agent_action_result }}
                    </div>
                </div>
                {% endif %}

                {% if error %}
                <div class="msg-row ai">
                    <div class="ai-avatar">⚠️</div>
                    <div class="bubble ai" style="color: #ff6b6b;">
                        **Erro de Conexão:** Houve um problema ao processar sua requisição ou a API de IA não respondeu. <br>Detalhe: {{ error }}
                    </div>
                </div>
                {% endif %}

                <div class="loading-overlay" id="loader">
                    <div class="typing-dots">
                        <span></span><span></span><span></span>
                    </div>
                </div>

            </div>

            <div class="input-area">
                <form method="POST" action="/" id="chatForm">
                    <div class="input-container">
                        <button type="button" id="recordButton" class="btn-action" title="Gravar voz">🎙️</button>
                        <textarea id="prompt" name="prompt" rows="1" placeholder="Peça um código, texto ou ajuda..." required>{{ previous_prompt_value }}</textarea>
                        <button type="submit" id="sendButton" class="btn-action btn-send" title="Enviar">➤</button>
                        <input type="hidden" name="agent_mode_state" id="agentModeState" value="{{ 'true' if agent_mode else 'false' }}">
                    </div>
                </form>
                <div class="footer-info">Luna pode cometer erros. Verifique informações importantes.</div>
            </div>

        </div>
    </div>

    <script>
        // --- 1. CONFIGURAÇÃO DO MARKDOWN (Marked.js) ---
        marked.use({
            breaks: true,
            gfm: true
        });

        // --- 2. RENDERIZAR RESPOSTA DA IA ---
        document.addEventListener('DOMContentLoaded', () => {
            const rawDataElement = document.getElementById('rawResponseData');
            const aiBubble = document.getElementById('aiResponse');

            if (rawDataElement && aiBubble) {
                const rawMarkdown = rawDataElement.textContent;

                aiBubble.innerHTML = marked.parse(rawMarkdown);
                hljs.highlightAll();
            }

            const messagesArea = document.getElementById('messagesArea');
            messagesArea.scrollTop = messagesArea.scrollHeight;
            autoResize();
        });

        // --- 3. LÓGICA DE INTERFACE ---
        const promptInput = document.getElementById('prompt');
        const chatForm = document.getElementById('chatForm');
        const loader = document.getElementById('loader');
        const messagesArea = document.getElementById('messagesArea');
        const recordButton = document.getElementById('recordButton');
        const editButton = document.getElementById('editButton');
        const stopButton = document.getElementById('stopButton');
        const aiActionsContainer = document.getElementById('aiActionsContainer');
        const agentModeButton = document.getElementById('agentModeButton');
        const agentModeState = document.getElementById('agentModeState');

        function autoResize() {
            promptInput.style.height = 'auto'; 
            promptInput.style.height = promptInput.scrollHeight + 'px';
        }
        promptInput.addEventListener('input', autoResize);

        promptInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (promptInput.value.trim() !== '') submitForm();
            }
        });

        document.getElementById('sendButton').addEventListener('click', (e) => {
            e.preventDefault();
            if (promptInput.value.trim() !== '') submitForm();
        });

        function submitForm() {
            loader.style.display = 'block';
            messagesArea.scrollTop = messagesArea.scrollHeight;
            chatForm.submit();
        }

        // --- LÓGICA MODO AGENTE ---
        agentModeButton.addEventListener('click', () => {
            const currentState = agentModeState.value === 'true';
            agentModeState.value = (!currentState).toString();

            chatForm.action = '/';
            chatForm.method = 'GET';
            chatForm.submit();
        });


        // --- LÓGICA DE BOTÕES DE AÇÃO ---

        if (editButton) {
            editButton.addEventListener('click', () => {
                const previousPrompt = '{{ previous_prompt | safe | replace("'", "\'") }}';

                promptInput.value = previousPrompt;
                autoResize();
                promptInput.focus();

                if (aiActionsContainer) {
                    aiActionsContainer.style.display = 'none';
                }
            });
        }

        if (stopButton) {
            stopButton.addEventListener('click', () => {
                if (confirm("Tem certeza que deseja cancelar e limpar o chat?")) {
                    window.location.href = '/'; 
                }
            });
        }

        // --- 4. RECONHECIMENTO DE VOZ ---
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SpeechRecognition) {
            const recognition = new SpeechRecognition();
            recognition.continuous = false;
            recognition.lang = 'pt-BR';

            recognition.onstart = () => { recordButton.classList.add('recording'); };
            recognition.onend = () => { recordButton.classList.remove('recording'); };
            recognition.onresult = (event) => {
                promptInput.value = event.results[0][0].transcript;
                autoResize();
            };

            recordButton.addEventListener('click', () => {
                if (recordButton.classList.contains('recording')) recognition.stop();
                else recognition.start();
            });
        } else {
            recordButton.style.display = 'none';
        }
    </script>
</body>
</html>
"""


# --- 3. BACKEND ---
@app.route('/', methods=['GET', 'POST'])
def index():
    # Variáveis de Estado
    response_text = None
    error = None
    previous_prompt = None
    previous_prompt_value = ""
    agent_mode = False
    screenshot_b64 = None
    agent_action_result = None

    # Verifica o estado do agente (GET)
    if request.method == 'GET':
        agent_mode_state = request.args.get('agent_mode_state')
        if agent_mode_state is not None:
            agent_mode = (agent_mode_state.lower() == 'true')
            return redirect(url_for('index', agent_mode_enabled=agent_mode))

        agent_mode = request.args.get('agent_mode_enabled', 'false').lower() == 'true'

    # Processamento do Prompt (POST)
    elif request.method == 'POST':
        prompt_raw = request.form.get('prompt', '')
        prompt = prompt_raw.strip()
        previous_prompt = prompt
        previous_prompt_value = prompt

        agent_mode = request.form.get('agent_mode_state', 'false').lower() == 'true'

        if prompt:
            # Lógica simples de identidade
            is_identity = any(re.search(r"\b" + re.escape(q) + r"\b", prompt.lower()) for q in
                              ["quem é vc", "quem é você", "qual seu nome", "fale sobre você"])

            if is_identity:
                response_text = "Eu sou **Luna**, sua assistente de IA. Estou aqui para ajudar com códigos e tarefas! Meu idioma é o **Português**."
                previous_prompt_value = ""

            elif agent_mode:
                # --- LÓGICA DO MODO AGENTE (MULTIMODAL) ---
                screenshot_b64 = take_screenshot_and_base64()

                if screenshot_b64:
                    # Estrutura Multimodal para a API
                    messages_data = [
                        {"role": "system", "content": SYSTEM_PROMPT_AGENTE},
                        {"role": "user", "content": [
                            {"type": "text", "text": f"Usuário pede: {prompt}"},
                            {"type": "image_url", "image_url": {"url": screenshot_b64}}
                        ]}
                    ]

                    data_openai = {
                        "model": MODELO_AGENTE_ESPECIFICO,
                        "messages": messages_data,
                        "temperature": 0.7,
                        "max_tokens": -1,
                        "stream": False
                    }
                    previous_prompt_value = ""

                else:
                    error = "Não foi possível tirar a captura de tela (PyAutoGUI/Pillow). Verifique as permissões do sistema."
                    data_openai = None

                if data_openai:
                    try:
                        # CORREÇÃO: Mantém timeout=5000 (5000 segundos) conforme solicitado.
                        response = requests.post(API_ENDPOINT, json=data_openai, timeout=5000)
                        response_json = None

                        # Tenta decodificar o JSON (Tratamento de erro robusto)
                        try:
                            response_json = response.json()
                        except json.JSONDecodeError:
                            if response.status_code != 200:
                                error = f"Erro HTTP {response.status_code}. API retornou corpo não JSON. Resposta: {response.text[:100]}..."

                        if response_json:
                            if response.status_code == 200:
                                # Processamento de resposta de sucesso (200)
                                if isinstance(response_json, dict) and 'choices' in response_json and len(
                                        response_json['choices']) > 0 and 'content' in response_json['choices'][0][
                                    'message']:

                                    raw_content = response_json['choices'][0]['message']['content'].strip()

                                    # DEBUG: Printa o conteúdo bruto antes de limpar/executar
                                    print(f"--- DEBUG RAW CONTENT ---\n{raw_content}\n--------------------------")

                                    # CORREÇÃO/AJUSTE: Regex mais robusta que busca o bloco, ignorando o que vier antes
                                    action_code_match = re.search(r"```python\n(.*?)```", raw_content, re.DOTALL)

                                    if action_code_match:
                                        action_code = action_code_match.group(1).strip()

                                        # DEBUG: Imprime o código extraído para confirmar
                                        print(
                                            f"--- DEBUG CÓDIGO EXTRAÍDO ---\n{action_code}\n------------------------------")

                                        agent_action_result = execute_agent_action(action_code)

                                        # Remove o bloco de código do conteúdo bruto
                                        response_text = re.sub(r"```python\n.*?```", "", raw_content,
                                                               flags=re.DOTALL).strip()

                                        # Se sobrar texto fora do bloco de código, limpa-o e exibe
                                        if response_text:
                                            response_text = clean_response(response_text)
                                        else:
                                            # Se não sobrou texto (apenas o bloco de código foi retornado),
                                            # exibe uma mensagem de texto simples
                                            response_text = "Ação de automação solicitada gerada e enviada para execução."


                                    # Se não houver bloco de código, trata a resposta como texto normal (pergunta/explicação)
                                    else:
                                        response_text = clean_response(raw_content)

                                else:
                                    error = f"API do LM Studio retornou JSON 200 inesperado. Estrutura de resposta inválida. Detalhes: {response_json}"

                            else:
                                # Trata erros HTTP (4xx/5xx) com JSON de erro
                                error_message = response_json.get('error', {}).get('message',
                                                                                   'Resposta da API não pôde ser lida.')
                                error = f"Erro HTTP {response.status_code} no modo Agente ({MODELO_AGENTE_ESPECIFICO}). Detalhe: {error_message}"

                    except requests.exceptions.ConnectionError:
                        error = f"Não foi possível conectar à API de IA em {API_BASE_URL}. Verifique a rede e se o serviço {MODELO_AGENTE_ESPECIFICO} está rodando no LM Studio."
                    except Exception as e:
                        error = f"Erro interno inesperado no Agente: {type(e).__name__}: {str(e)}"

            else:
                # --- LÓGICA DO MODO TEXTO NORMAL (Chat Simples) ---
                data_openai = {
                    "model": MODELO_TEXTO_PADRAO,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT_CHAT},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.7
                }

                try:
                    # CORREÇÃO: Mantém timeout=5000 (5000 segundos) conforme solicitado.
                    response = requests.post(API_ENDPOINT, json=data_openai, timeout=5000)
                    response_json = response.json()

                    if response.status_code == 200:
                        raw_content = response_json['choices'][0]['message']['content'].strip()
                        response_text = clean_response(raw_content)
                        previous_prompt_value = ""
                    else:
                        error = f"Erro HTTP {response.status_code}. Detalhe: {response_json.get('error', {}).get('message', 'Resposta da API não pôde ser lida.')}"

                except requests.exceptions.ConnectionError:
                    error = f"Não foi possível conectar à API de IA em {API_BASE_URL}. Verifique a rede e se o serviço está rodando."
                except Exception as e:
                    error = f"Erro interno inesperado: {type(e).__name__}: {str(e)}"

    return render_template_string(
        HTML_TEMPLATE,
        response_text=response_text,
        error=error,
        previous_prompt=previous_prompt,
        previous_prompt_value=previous_prompt_value,
        agent_mode=agent_mode,
        screenshot_b64=screenshot_b64,
        agent_action_result=agent_action_result,
        MODELO_AGENTE_ESPECIFICO=MODELO_AGENTE_ESPECIFICO
    )


if __name__ == '__main__':
    print("--- LUNA IA (Agente Multimodal) ---")
    print(f"Alvo da IA: {API_ENDPOINT}")
    print(f"Modelo Agente: {MODELO_AGENTE_ESPECIFICO}")
    # Configurado para rodar em 0.0.0.0 (acessível na rede local) na porta 5000.
    app.run(debug=True, host='0.0.0.0', port=5000)