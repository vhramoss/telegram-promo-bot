# 🤖 Bot de Promoções para Telegram

Bot Python que monitora sites brasileiros de promoções (Pelando, Promobit, Promocoes Nerd, Cupom Válido) e posta automaticamente as melhores ofertas no seu canal do Telegram — com dashboard web para monitorar tudo sem precisar de terminal.

## Funcionalidades

- Busca promoções de 4 fontes RSS em paralelo a cada 15 minutos
- Filtra duplicatas com SQLite (nunca posta o mesmo deal duas vezes)
- Posta com foto quando disponível, fallback para texto
- Dashboard web com métricas, deals recentes e logs em tempo real
- Roda 24/7 no Railway (deploy gratuito com 1 comando)

---

## Configuração — Passo a passo

### 1. Criar o bot no Telegram (2 min)

1. Abra o Telegram e pesquise por `@BotFather`
2. Envie `/newbot`
3. Escolha um nome (ex: "Promoções do Victor") e um username (ex: `VictorPromosBot`)
4. O BotFather vai te dar um **token** — guarde, você vai precisar

### 2. Criar o canal no Telegram

1. No Telegram: **Nova conversa → Novo Canal**
2. Defina o nome e o username público (ex: `@meucanaldeofertas`)
3. Adicione o bot como **administrador** do canal (com permissão de postar mensagens)

### 3. Configurar as variáveis de ambiente

```bash
cp .env.example .env
```

Edite o `.env` e preencha:

```env
TELEGRAM_TOKEN=1234567890:ABCDefgh...   # token do BotFather
TELEGRAM_CHANNEL=@meucanaldeofertas    # username do seu canal
```

### 4. Rodar localmente (para testar)

```bash
# Instalar dependências
pip install -r requirements.txt

# Iniciar o bot
python bot.py
```

Acesse o dashboard em: **http://localhost:5000**

---

## Deploy no Railway (produção 24/7)

### Pré-requisitos
- Conta gratuita em [railway.app](https://railway.app)
- Git instalado

### Passos

```bash
# 1. Inicializar o repositório git (se ainda não tiver)
git init
git add .
git commit -m "feat: bot de promoções telegram"

# 2. Criar repositório no GitHub e subir
# (crie em github.com/new como privado, depois:)
git remote add origin https://github.com/vhramoss/telegram-promo-bot.git
git push -u origin main
```

No Railway:
1. Acesse [railway.app](https://railway.app) → **New Project → Deploy from GitHub repo**
2. Selecione o repositório `telegram-promo-bot`
3. Vá em **Variables** e adicione:
   - `TELEGRAM_TOKEN` = seu token
   - `TELEGRAM_CHANNEL` = @seu_canal
4. Clique em **Deploy** — pronto! 🚀

O Railway detecta o `Procfile` automaticamente e sobe o bot. O dashboard fica disponível na URL pública que o Railway gera.

---

## Estrutura do projeto

```
telegram-promo-bot/
├── bot.py           # Núcleo: scheduler + Telegram + Flask
├── scraper.py       # Busca RSS nas 4 fontes em paralelo
├── database.py      # SQLite: deals, logs, estatísticas
├── templates/
│   └── index.html   # Dashboard web de monitoramento
├── .env.example     # Modelo das variáveis de ambiente
├── requirements.txt # Dependências Python
├── Procfile         # Comando de inicialização (Railway)
└── README.md
```

---

## Adicionando novas fontes de promoção

Edite `scraper.py` e adicione um item na lista `RSS_FEEDS`:

```python
{
    "name": "Minha Fonte",
    "url": "https://www.minhafonte.com.br/feed/",
    "emoji": "⚡",
},
```

Qualquer site com feed RSS funciona automaticamente.

---

## Variáveis de ambiente

| Variável                 | Obrigatório | Descrição                               | Padrão |
|--------------------------|-------------|------------------------------------------|--------|
| `TELEGRAM_TOKEN`         | ✅ Sim      | Token do bot (BotFather)                | —      |
| `TELEGRAM_CHANNEL`       | ✅ Sim      | Username ou ID do canal                  | —      |
| `CHECK_INTERVAL_MINUTES` | Não         | Minutos entre verificações              | 15     |
| `MAX_DEALS_PER_RUN`      | Não         | Máx. de deals postados por rodada       | 5      |
| `PORT`                   | Não         | Porta do dashboard (Railway define auto)| 5000   |
| `DB_PATH`                | Não         | Caminho do arquivo SQLite               | deals.db |
