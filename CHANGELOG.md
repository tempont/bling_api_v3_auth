# Changelog

Todas as mudanças relevantes deste projeto são documentadas aqui.
O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto
adota [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [1.0.0] - Não lançado

Primeira versão publicada no PyPI como `bling-api-v3-auth`.

### Adicionado

- Pacote instalável (`pip install bling-api-v3-auth`) com tipagem (`py.typed`).
- Suporte a **tokens JWT**: o header `enable-jwt: 1` é enviado na troca do `code` e em
  todo refresh (tokens opacos estão descontinuados pelo Bling).
- `BlingAuthManager`: renovação automática e proativa do access token, serializada por
  lock (o Bling rotaciona o refresh token a cada uso).
- `BlingAuth`: integração com `requests` (`session.auth = manager.auth()`), com uma nova
  tentativa automática após `401`.
- Armazenamentos `JsonTokenStorage` (escrita atômica, permissão `0600`),
  `RedisTokenStorage` (TTL + lock distribuído) e `MemoryTokenStorage`; interface
  `TokenStorage` para backends próprios.
- Revogação de tokens (`/oauth/revoke`, com `revoke_action` e `revoke_target`).
- Geração de `state` aleatório na URL de autorização (proteção contra CSRF).
- CLI `bling-auth` (`login`, `url`, `authorize`, `token`, `status`, `revoke`).
- Exceções `BlingOAuthError` (com `status_code`, `error`, `description`),
  `AuthorizationRequiredError` e `BlingConfigError`.
- Testes (Python 3.10 a 3.14), CI no GitHub Actions e publicação no PyPI via
  Trusted Publishing.

### Alterado

- Endpoints de token e revogação passam a usar `https://api.bling.com.br/Api/v3/oauth/*`.
- Header `Accept: 1.0`, conforme exemplos oficiais.
- Validade padrão do access token passa de 1 h para 6 h (`expires_in` retornado pelo
  Bling continua tendo prioridade).
- Configuração lida sob demanda (`BlingConfig.from_env()`), sem efeitos colaterais na
  importação; leitura de `.env` agora é opcional (extra `dotenv`).
- Redis passa a ser um extra opcional (`bling-api-v3-auth[redis]`) e guarda os tokens em
  uma única chave JSON.

### Corrigido

- Redis sem o extra opcional agora gera `BlingConfigError` com a instrução de
  instalação, também ao usar `BLING_TOKEN_STORAGE=redis` com URL padrão ou explícita.
- JSON de credenciais malformado agora gera `AuthorizationRequiredError`:
  `bling-auth status` e `bling-auth token` exibem uma mensagem com o caminho do
  arquivo e a instrução para autorizar novamente, sem traceback ou conteúdo dos tokens.

### Removido

- Scripts em `app/` (`BlingApiTokenHandler`, `TokenStorage` estático, `main.py`) e os
  arquivos `requirements*.txt`. Veja a seção "Migrando da versão em `app/`" no README.

### Compatibilidade

- O arquivo `credential/credentials.json` gerado pela versão antiga continua sendo lido
  (`JsonTokenStorage("credential/credentials.json")`).
- As variáveis `TOKENS_STORAGE_METHOD`, `REDIS_HOST_IP`, `REDIS_HOST_PORT`,
  `REDIS_PASSWORD` e `ACCESS_TOKEN_EXPIRY_SKEW` continuam aceitas.

[1.0.0]: https://github.com/tempont/bling_api_v3_auth/releases/tag/v1.0.0
