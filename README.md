# bling-api-v3-auth

[![PyPI](https://img.shields.io/pypi/v/bling-api-v3-auth)](https://pypi.org/project/bling-api-v3-auth/)
[![Python](https://img.shields.io/pypi/pyversions/bling-api-v3-auth)](https://pypi.org/project/bling-api-v3-auth/)
[![CI](https://github.com/tempont/bling_api_v3_auth/actions/workflows/ci.yml/badge.svg)](https://github.com/tempont/bling_api_v3_auth/actions/workflows/ci.yml)
[![License: Unlicense](https://img.shields.io/badge/license-Unlicense-blue.svg)](https://github.com/tempont/bling_api_v3_auth/blob/main/LICENSE)

Autenticação OAuth 2.0 **leve** para a [API v3 do Bling ERP](https://developer.bling.com.br),
já preparada para os **tokens JWT**. Ela cuida de:

- montar a URL de autorização (com `state` contra CSRF) e trocar o `code` por tokens;
- guardar os tokens (JSON local, Redis, memória ou o seu próprio backend);
- **renovar o access token automaticamente**, sem renovações concorrentes (o Bling rotaciona o refresh token a cada uso);
- assinar requisições do `requests`, com uma nova tentativa automática em caso de `401`;
- revogar tokens;
- tudo isso também pela linha de comando, com `bling-auth`.

A única dependência obrigatória é o `requests`. Redis e `.env` são opcionais.

> English version: [docs/README.en.md](https://github.com/tempont/bling_api_v3_auth/blob/main/docs/README.en.md)

---

## Sumário

- [Instalação](#instalação)
- [Pré-requisitos no Bling](#pré-requisitos-no-bling)
- [Início rápido (CLI)](#início-rápido-cli)
- [Uso no código](#uso-no-código)
- [Armazenamento dos tokens](#armazenamento-dos-tokens)
- [Configuração](#configuração)
- [Tokens JWT: o que mudou](#tokens-jwt-o-que-mudou)
- [Regras do Bling que você precisa conhecer](#regras-do-bling-que-você-precisa-conhecer)
- [Erros](#erros)
- [Migrando da versão em `app/`](#migrando-da-versão-em-app)
- [Desenvolvimento](#desenvolvimento)
- [Publicação no PyPI](#publicação-no-pypi)

## Instalação

```bash
pip install bling-api-v3-auth

# opcionais
pip install "bling-api-v3-auth[dotenv]"        # ler variáveis de um arquivo .env
pip install "bling-api-v3-auth[redis]"         # armazenar tokens no Redis
pip install "bling-api-v3-auth[redis,dotenv]"
```

O pacote requer Python 3.10 ou superior.

## Pré-requisitos no Bling

1. No Bling, acesse **Central de Extensões › Área do Integrador** e cadastre um aplicativo
   ([documentação](https://developer.bling.com.br/aplicativos)).
2. Informe o **link de redirecionamento** (callback) e escolha os **escopos**.
   O Bling sempre usa os valores cadastrados no app, mesmo que você envie outros na URL.
   Alterar os escopos depois revoga o acesso de todos os usuários do app.
3. Copie o `client_id` e o `client_secret`.

Para obter o `code` manualmente, use o **Link de convite** do aplicativo. Depois de autorizar,
o Bling redireciona para o seu callback com `?code=...&state=...`:

![Link de convite no Bling](https://raw.githubusercontent.com/tempont/bling_api_v3_auth/main/code-link-bling.jpg)

## Início rápido (CLI)

```bash
export BLING_CLIENT_ID=seu_client_id
export BLING_CLIENT_SECRET=seu_client_secret
# ou coloque as variáveis em um .env (requer o extra [dotenv])

bling-auth login     # mostra a URL; cole a URL de retorno (ou só o code)
bling-auth status    # validade dos tokens (nunca imprime os tokens)
bling-auth token     # imprime um access token válido, renovando se preciso
bling-auth revoke    # revoga no Bling e apaga localmente
```

Outros comandos: `bling-auth url` (só gera a URL) e `bling-auth authorize <code|url>`.
Use `--env-file caminho/.env` para apontar outro arquivo.

> O `code` vale **cerca de 1 minuto** e só pode ser usado **uma vez**.

## Uso no código

### Com `requests` (recomendado)

```python
import requests
from bling_api_v3_auth import API_BASE_URL, BlingAuthManager

manager = BlingAuthManager.from_env()  # BLING_* do ambiente; armazenamento JSON padrão

session = requests.Session()
session.auth = manager.auth()  # adiciona Authorization (+ enable-jwt) e renova sozinho

resp = session.get(f"{API_BASE_URL}/produtos", params={"limite": 100}, timeout=30)
resp.raise_for_status()
print(resp.json()["data"])
```

Se o Bling responder `401` (por exemplo, com o token revogado), o `BlingAuth` renova o token
**uma vez** e repete a requisição. Para desativar esse comportamento, use
`BlingAuth(manager, retry_on_401=False)`.

### Só os headers (para `httpx`, `aiohttp` etc.)

```python
headers = manager.headers()
# {'Authorization': 'Bearer eyJ...', 'enable-jwt': '1'}

token = manager.get_access_token()  # só a string do token
```

### Fluxo de autorização em uma aplicação web

```python
from bling_api_v3_auth import BlingAuthManager, BlingConfig, JsonTokenStorage

manager = BlingAuthManager(
    BlingConfig(client_id="...", client_secret="..."),
    JsonTokenStorage("./credential/credentials.json"),
)

# 1. Redirecione o usuário e guarde o state (ex.: na sessão)
url, state = manager.authorization_url()

# 2. No callback: GET /callback?code=...&state=...
if request.args["state"] != state:
    abort(400)  # possível CSRF
manager.authorize(request.args["code"])

# 3. Em qualquer lugar da aplicação
manager.headers()
```

Se o usuário negar o acesso, o callback recebe `?error=access_denied&error_description=...`
em vez de `code`.

Veja também a pasta [`examples/`](https://github.com/tempont/bling_api_v3_auth/blob/main/examples/).

### API de baixo nível

O `BlingOAuthClient` só faz as chamadas HTTP e não guarda nada. É útil quando você mesmo
controla o armazenamento:

```python
from bling_api_v3_auth import BlingConfig, BlingOAuthClient

client = BlingOAuthClient(BlingConfig.from_env())
token = client.exchange_code(code)  # TokenData
token = client.refresh(token.refresh_token)
client.revoke(token.refresh_token, token_type_hint="refresh_token")
```

## Armazenamento dos tokens

| Backend | Uso | Observações |
| --- | --- | --- |
| `JsonTokenStorage(path)` | padrão | Arquivo JSON com permissão `0600` e escrita atômica. Caminho padrão: `~/.config/bling_api_v3_auth/credentials.json`. |
| `RedisTokenStorage(client, key=...)` | vários processos ou servidores | Requer o extra `[redis]`. A chave expira junto com o refresh token. Renovações protegidas por **lock distribuído**. |
| `MemoryTokenStorage()` | testes e scripts curtos | Não persiste nada. |

Para usar outro backend (banco de dados, secret manager...), herde de `TokenStorage`:

```python
from bling_api_v3_auth import TokenData, TokenStorage


class DatabaseStorage(TokenStorage):
    def load(self) -> TokenData | None: ...
    def save(self, token: TokenData) -> None: ...  # use token.to_dict()
    def clear(self) -> None: ...

    # opcional: sobrescreva lock() se vários processos compartilham o token
```

> Com tokens JWT, o access token tem cerca de **1.500 a 3.000 caracteres**. Em banco de dados,
> use colunas `TEXT`, não `VARCHAR(255)`.

## Configuração

`BlingConfig.from_env()` e a CLI leem as variáveis abaixo. O arquivo
[`.env.example`](https://github.com/tempont/bling_api_v3_auth/blob/main/.env.example) traz um modelo.

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `BLING_CLIENT_ID` | obrigatória | `client_id` do aplicativo |
| `BLING_CLIENT_SECRET` | obrigatória | `client_secret` do aplicativo |
| `BLING_REDIRECT_URI` | não informado | Envia `redirect_uri` na URL de autorização |
| `BLING_ENABLE_JWT` | `true` | Envia `enable-jwt: 1` para receber tokens JWT |
| `BLING_REFRESH_SKEW` | `60` | Renova o token N segundos antes de expirar |
| `BLING_TIMEOUT` | `30` | Timeout das chamadas OAuth (s) |
| `BLING_AUTHORIZE_URL` | `https://www.bling.com.br/Api/v3/oauth/authorize` | |
| `BLING_TOKEN_URL` | `https://api.bling.com.br/Api/v3/oauth/token` | |
| `BLING_REVOKE_URL` | `https://api.bling.com.br/Api/v3/oauth/revoke` | |
| `BLING_TOKEN_STORAGE` | `json` | `json`, `redis` ou `memory` |
| `BLING_TOKEN_FILE` | `~/.config/bling_api_v3_auth/credentials.json` | Caminho do JSON |
| `BLING_REDIS_URL` | `redis://localhost:6379/0` | Conexão do Redis |
| `BLING_REDIS_KEY` | `bling_api_v3_auth:token` | Chave no Redis (use uma por conta Bling) |

`BlingConfig.from_env(env_file=".env")` lê o arquivo com o extra `[dotenv]`. Variáveis já
definidas no ambiente têm prioridade, e o `os.environ` não é alterado.

## Tokens JWT: o que mudou

O Bling [descontinuou os tokens opacos](https://developer.bling.com.br/migracao-jwt). A data de
bloqueio ainda não foi publicada. Na prática:

- O JWT só é emitido quando a requisição ao `/oauth/token` traz o header **`enable-jwt: 1`**,
  tanto na troca do `code` quanto **em todo refresh**. Sem ele, o Bling continua devolvendo
  um token opaco. Esta biblioteca envia o header por padrão.
- Nas chamadas à API, a biblioteca envia `Authorization: Bearer <token>` e acrescenta
  `enable-jwt: 1` **apenas quando o token é um JWT**, porque há relatos de `401` quando um
  token opaco é enviado com esse header.
- O token fica bem maior (cerca de 1.500 a 3.000 caracteres). Ajuste colunas e logs.
- Tokens opacos já salvos continuam funcionando até a migração total do Bling, e os
  próximos refreshes já são feitos com `enable-jwt: 1`. Se algo falhar, basta autorizar
  novamente com `bling-auth login`.

## Regras do Bling que você precisa conhecer

| Regra | Valor |
| --- | --- |
| Validade do `code` | ~1 minuto, **uso único**. Reusar um `code` **revoga o acesso do usuário**. |
| Validade do access token | `expires_in` da resposta (atualmente 21600 s = 6 h) |
| Validade do refresh token | 30 dias. Um novo é emitido a cada refresh, e o anterior deixa de valer. |
| Limite em `/oauth/token` | 20 requisições/minuto por IP. Acima disso, **bloqueio de 60 min**. |
| Limite da API | 3 requisições/s e 120.000/dia por conta |

Como a biblioteca lida com isso:

- renova o token **antes** de expirar e só quando necessário, sem gastar o limite do `/oauth/token`;
- serializa as renovações com lock, para que duas renovações simultâneas não invalidem uma à outra;
- se o refresh token expirar (mais de 30 dias sem uso) ou for revogado, lança
  `AuthorizationRequiredError`. Nesse caso é preciso autorizar de novo (`bling-auth login`).

> Para não perder o refresh token, garanta que a aplicação renove os tokens ao menos uma vez
> a cada 30 dias. Por exemplo, um cron diário com `bling-auth token > /dev/null`.

## Erros

Todas as exceções herdam de `BlingApiError`:

| Exceção | Quando |
| --- | --- |
| `BlingConfigError` | `client_id`/`client_secret` ausentes ou valor inválido |
| `BlingOAuthError` | Falha HTTP ou de rede nos endpoints OAuth. Atributos: `status_code`, `error` (ex.: `invalid_client`), `description`, `response_body`. |
| `AuthorizationRequiredError` | Não há tokens salvos, ou o Bling recusou o refresh token (`invalid_grant`). Autorize novamente. |

```python
from bling_api_v3_auth import AuthorizationRequiredError, BlingOAuthError

try:
    headers = manager.headers()
except AuthorizationRequiredError:
    ...  # redirecione o usuário para manager.authorization_url()
except BlingOAuthError as exc:
    log.error("Bling OAuth falhou: %s (%s)", exc.error, exc.status_code)
```

## Migrando da versão em `app/`

As versões anteriores eram scripts em `app/`. A partir da 1.0, o projeto é um pacote instalável.

| Antes | Agora |
| --- | --- |
| `python app/main.py` | `bling-auth login` e `bling-auth token` |
| `BlingApiTokenHandler().get_token_using_code(code)` | `manager.authorize(code)` |
| `BlingApiTokenHandler().refresh_tokens(rt)` | `manager.refresh()` (ou automático) |
| `get_valid_access_token(storage, handler)` | `manager.get_access_token()` |
| `TokenStorage.retrieve_token_by_key("access_token")` | `manager.storage.load().access_token` |
| `TOKENS_STORAGE_METHOD=json\|redis` | `BLING_TOKEN_STORAGE=json\|redis` (o nome antigo ainda funciona) |
| `REDIS_HOST_IP` / `REDIS_HOST_PORT` / `REDIS_PASSWORD` | `BLING_REDIS_URL` (as antigas ainda funcionam) |
| `credential/credentials.json` | `~/.config/bling_api_v3_auth/credentials.json` |

O arquivo antigo pode ser reaproveitado sem nova autorização:

```bash
export BLING_TOKEN_FILE=./credential/credentials.json
bling-auth status
```

No Redis, a versão antiga gravava duas chaves (`access_token` e `refresh_token`). A nova grava
um único JSON em `BLING_REDIS_KEY`, então é preciso autorizar de novo uma vez.

## Desenvolvimento

O projeto usa [uv](https://docs.astral.sh/uv/).

```bash
uv sync                          # cria .venv com as dependências de desenvolvimento
uv run pytest --cov              # testes
uv run ruff check . && uv run ruff format --check .
uv run basedpyright              # checagem de tipos
uv build                         # gera wheel e sdist em dist/
```

A CI (`.github/workflows/ci.yml`) roda lint, tipos e testes no Python 3.10 a 3.14, além de
um teste do wheel gerado.

## Publicação no PyPI

A publicação usa [Trusted Publishing](https://docs.pypi.org/trusted-publishers/), sem token
salvo no GitHub.

**Configuração (uma vez):**

1. Em [pypi.org](https://pypi.org/manage/account/publishing/), vá em **Publishing › Add a new pending publisher**:
   - project: `bling-api-v3-auth`
   - owner: `tempont`
   - repository: `bling_api_v3_auth`
   - workflow: `publish.yml`
   - environment: `pypi`
2. No GitHub, em **Settings › Environments**, crie o environment `pypi`. Se quiser, adicione
   revisores obrigatórios.
3. Opcional: repita os passos 1 e 2 em [test.pypi.org](https://test.pypi.org) com o
   environment `testpypi`.

**A cada versão:**

1. Atualize `src/bling_api_v3_auth/_version.py` e o `CHANGELOG.md`.
2. Faça o merge na `main`.
3. Crie uma **Release** no GitHub com a tag `vX.Y.Z`, igual à versão do pacote. O workflow
   `publish.yml` valida a tag, gera os pacotes e publica no PyPI.

Para testar antes, rode o workflow **Publish** manualmente (*Run workflow*). Ele publica no
TestPyPI.

## Projetos relacionados

- [`bling-jwt-auth`](https://github.com/tempont/bling-jwt-auth-python): alternativa baseada
  em `httpx` e `pydantic`, com armazenamento SQLite.

## Licença

[Unlicense](https://github.com/tempont/bling_api_v3_auth/blob/main/LICENSE): domínio público.
