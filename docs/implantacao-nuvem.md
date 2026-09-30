# Preparação para a nuvem

Checklist e decisões para o futuro deploy. **Nada disto está configurado ainda**: hoje o Rodagem roda só localmente (SQLite, servidor em `127.0.0.1`). Itens marcados como "verificado" foram testados neste repositório; os demais são pendências.

## 1. Variáveis de ambiente

| Variável | Uso | Produção |
|---|---|---|
| `DJANGO_DEBUG` | `1` liga o modo de desenvolvimento | `0` (obrigatório) |
| `DJANGO_SECRET_KEY` | Chave secreta | Obrigatória com `DJANGO_DEBUG=0`; gerada e guardada no cofre do provedor, nunca no repositório |
| `DJANGO_ALLOWED_HOSTS` | Domínios aceitos, separados por vírgula | Só o domínio público |
| `RODAGEM_DB_PATH` | Caminho do SQLite | Não se aplica com PostgreSQL (seção 6) |
| `RODAGEM_MEDIA_ROOT` | Pasta dos anexos | Volume persistente e privado (seção 7) |
| `RODAGEM_TIME_ZONE` | Fuso horário (padrão `America/Sao_Paulo`) | Conforme o público |
| `RODAGEM_COOKIE_SUFFIX` | Nomes de cookie próprios | Só para instâncias de teste na mesma máquina; não usar em produção |

Com `DJANGO_DEBUG=0` já ficam ligados: cookies seguros, redirecionamento para HTTPS e HSTS de 1 ano.

## 2. Arquivos estáticos com hash no nome (verificado)

Problema visto nos fluxos: depois de atualizar o `app.js`, o navegador continuou com a versão antiga em cache. Com nomes versionados (`app.7508158fa184.css`), cada atualização gera uma URL nova e o cache longo passa a ser seguro.

O armazenamento padrão do WhiteNoise (`CompressedManifestStaticFilesStorage`) **falha** neste projeto, porque o `bootstrap.min.css` aponta para um mapa de origem (`bootstrap.min.css.map`) que não está no repositório. Solução testada: uma subclasse que ignora referências ausentes.

```python
# config/storage.py
from whitenoise.storage import CompressedManifestStaticFilesStorage


class ForgivingManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    def hashed_name(self, name, content=None, filename=None):
        try:
            return super().hashed_name(name, content, filename)
        except ValueError:
            return name
```

```python
# config/settings.py (só fora do modo debug)
if not DEBUG:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "config.storage.ForgivingManifestStaticFilesStorage"},
    }
```

Resultado do teste com `collectstatic`: 13 arquivos copiados, 33 processados, e `{% static %}` devolve `/static/app.<hash>.css`. Rodar `collectstatic --noinput` a cada deploy. Em desenvolvimento nada muda, e os testes continuam sem o manifesto.

Codificação: `app.css` e `app.js` são servidos sem `charset`, e um navegador leu um caractere UTF-8 do CSS como Windows-1252 ("−" virou "âˆ’"). Esses arquivos agora são só ASCII (escapes como `\2212`), e um teste impede regressões. Ao publicar, confirmar que CSS e JS saem com `Content-Type` contendo `charset=utf-8`.

## 3. HTTPS atrás de proxy

O provedor normalmente termina o HTTPS e repassa HTTP ao aplicativo. Sem ajuste, `SECURE_SSL_REDIRECT` entra em laço de redirecionamento.

- `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`, **só** se o proxy do provedor sobrescrever esse cabeçalho (nunca aceitá-lo de clientes).
- `CSRF_TRUSTED_ORIGINS = ["https://seu-dominio"]` se os envios de formulário forem recusados com 403.
- `manage.py check --deploy` (verificado, com `DEBUG=0`) só acusa `W005` (HSTS em subdomínios) e `W021` (HSTS preload). São opcionais; ligar só se todos os subdomínios forem exclusivamente HTTPS.

## 4. Primeira conta (risco de segurança, pendente)

`garage/views.py` (`setup`) só aceita criar a primeira conta quando `REMOTE_ADDR` é `127.0.0.1` ou `::1`. Atrás de um proxy no mesmo servidor, **toda** requisição parece local, e qualquer pessoa que alcançar a URL antes do dono poderia criar a conta.

Decisão pendente, uma das opções:
- criar o primeiro usuário por comando de gerenciamento no servidor e desativar `/conta/iniciar/` em produção (recomendado);
- exigir um token de uso único definido em variável de ambiente.

## 5. Bloqueio de tentativas de login atrás de proxy (pendente)

O `django-axes` bloqueia por usuário + IP. Atrás de proxy, o IP visto é o do proxy, e uma pessoa mal-intencionada poderia bloquear o login de todos errando a senha de um usuário. Configurar `AXES_IPWARE_PROXY_COUNT` (ou a ordem dos cabeçalhos em `AXES_IPWARE_META_PRECEDENCE_ORDER`) conforme o provedor, e testar com a versão instalada (8.3.1).

## 6. Banco de dados (pendente)

SQLite serve para uso local. Na nuvem, migrar para PostgreSQL gerenciado:
- adicionar o driver (`psycopg`) aos requisitos e ler a conexão de variável de ambiente (`DATABASE_URL` ou equivalente);
- rodar `manage.py migrate` no deploy;
- confirmar que o teste de ida e volta do backup (`reports/tests.py`) e as restrições únicas (uma leitura por veículo por dia) passam no PostgreSQL;
- o `select_for_update` usado ao gravar leituras passa a ter efeito real, o que é desejável.

## 7. Anexos privados (pendente)

Os anexos ficam em `MEDIA_ROOT` e só são servidos por uma rota que confere o dono. Em nuvem:
- volume persistente (ou armazenamento de objetos privado) montado em `RODAGEM_MEDIA_ROOT`; discos efêmeros perdem os arquivos a cada deploy;
- nunca expor a pasta por URL pública;
- incluir a pasta no backup.

## 8. Servidor de aplicação

`waitress` já está nos requisitos e funciona em Linux: `waitress-serve --listen=0.0.0.0:$PORT config.wsgi:application` atrás do proxy do provedor. Nunca usar `runserver`. Com SQLite, manter um único processo; com PostgreSQL, mais processos são possíveis.

## 9. Backup e recuperação

- Banco: backup automático do PostgreSQL gerenciado e teste de restauração antes de usar de verdade.
- Dados do usuário: o backup `.zip` pela interface e o comando `export_backup` continuam valendo; agendar o comando no provedor.
- A senha não faz parte do backup.

## 10. Decisões de produto para usuários reais (pendentes)

- **Cadastro de outras pessoas:** hoje só existe a primeira conta (`Installation`). Definir se o serviço será de uma pessoa só ou com cadastro aberto/por convite; isso muda as seções 4 e 5.
- **Recuperação de senha:** não há e-mail; quem perde a senha depende do operador. Definir o processo.
- **Privacidade:** o que é coletado (veículos, placa, anexos), por quanto tempo é guardado e como a pessoa exclui a conta e os dados (não há exclusão de conta pela interface).
- **Acessibilidade:** o Fluxo 10 (teclado, 320 px, zoom de 200%, contraste, movimento reduzido) precisa estar aprovado antes de abrir para o público.

## 11. Checklist antes do primeiro deploy

1. Fluxos de interface 1 a 10 aprovados (`docs/fluxos-de-interface.md`).
2. `manage.py test garage maintenance planning reports assistant` e as jornadas com `RUN_BROWSER_TESTS=1` passando.
3. Estáticos com hash (seção 2) e `collectstatic` no deploy.
4. `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY` e `DJANGO_ALLOWED_HOSTS` definidos; `manage.py check --deploy` sem alertas além de `W005` e `W021`.
5. Proxy, CSRF e bloqueio de login ajustados (seções 3 e 5).
6. Primeira conta criada sem janela aberta (seção 4).
7. PostgreSQL e anexos persistentes (seções 6 e 7), com backup testado.
8. Nenhum dado pessoal no repositório, no histórico ou nos exemplos (`docs/licoes-aprendidas.md`).
