# 🌙 Luna IA: Assistente Multimodal & Agente de Automação

A **Luna IA** é uma interface inteligente desenvolvida em Flask que combina as capacidades de um chat convencional com um **Agente Multimodal**. Ela é capaz de "ver" o teu ecrã através de capturas (screenshots), analisar o contexto visual e executar ações diretamente no Sistema Operacional (**Ubuntu/GNOME**) utilizando comandos de teclado e rato.

## ✨ Funcionalidades

* **Modo Chat:** Conversa textual inteligente para dúvidas e suporte.
* **Modo Agente (Vision):** A Luna captura o ecrã, envia para um modelo Vision (como o Llava) e gera código Python em tempo real para automação.
* **Interface Dark Neon:** UI moderna e responsiva com foco em estética e usabilidade.
* **Navegação Otimizada:** Programada para usar atalhos universais (ex: `Ctrl+L` para navegação web), garantindo estabilidade no Linux.
* **Rolagem Flexbox:** Área de mensagens com rolagem vertical automática e layout otimizado para não quebrar em diferentes tamanhos de ecrã.
* **Voz para Texto:** Integração com a Web Speech API para comandos por voz.

## 🚀 Tecnologias Utilizadas

* **Backend:** Python 3.10+ / Flask.
* **Automação:** PyAutoGUI / Pillow (PIL).
* **IA/LLM:** LM Studio (API compatível com OpenAI).
* **Frontend:** HTML5, CSS3 (Flexbox/Variables), JavaScript (Marked.js, Highlight.js).

## 📋 Pré-requisitos

1.  **LM Studio:** Instalado e em execução.
2.  **Modelos Recomendados:**
    * Texto: `openai/gpt-oss-20b` (ou similar).
    * Vision: `llava-llama-3-8b-v1_1` (necessário para o Modo Agente).
3.  **Dependências Python:**
    ```bash
    pip install flask requests pyautogui pillow
    ```

## ⚙️ Configuração

No ficheiro `main.py`, certifica-te de que o endereço do servidor LM Studio está correto:

```python
API_BASE_URL = "[http://192.168.15.7:1234](http://192.168.15.7:1234)" # Altera para o IP da tua máquina se necessário
