# Lições aprendidas

Registro do que já custou tempo nos incrementos 1 e 2. Leia antes de mudar regras de quilometragem, anexos, formulários ou testes de navegador.

## Ambiente (Windows)

- Use sempre `.\.venv\Scripts\python.exe` (Python 3.13). O VS Code pode sugerir o Python global 3.14; não use.
- No PowerShell, `Select-String` e `Get-NetTCPConnection` sem resultado devolvem código de saída 1. Leia a saída (`OK`, `Ran N tests`) antes de concluir que algo falhou.
- Linhas `System.Management.Automation.RemoteException` e `AXES: ...` na saída dos testes são ruído de stderr, não erros.
- Porta ocupada: verifique com `Get-NetTCPConnection -LocalPort 8000 -State Listen` antes de iniciar outro servidor.
- O Windows bloqueia arquivos abertos. Exclusão de anexo com o arquivo ainda aberto gera `PermissionError`.
- Git: `Rename from .git/index.lock ... failed. Should I try again? (y/n)` ocorre quando o VS Code lê o repositório ao mesmo tempo. Responda `y`; não apague o `index.lock` enquanto houver processo Git ativo. Faça commits um por comando, sem encadear vários, para o prompt não consumir o comando seguinte.
- Identidade do Git somente com `git config --local`; nunca altere a configuração global.

## Repositório público

- O repositório é público e a aplicação é genérica: nada de dados de um carro, pessoa ou cidade específicos no código, nos testes ou na documentação (nem como atalho ou exemplo). Dados reais são cadastrados pela interface; exemplos usam veículos fictícios ("Exemplo Compacto 2020"). Configurações regionais vêm de variáveis de ambiente (`RODAGEM_TIME_ZONE`).
- Commits usam o e-mail noreply do GitHub (`git config --local user.email`). Um e-mail pessoal publicado exige reescrever o histórico e fazer force push.
- Antes de publicar, busque segredos e dados pessoais em todas as revisões (`git grep ... $(git rev-list --all)`), não só nos arquivos atuais.
- Senhas nos testes são fictícias e usadas apenas em bancos temporários.

## Regras de domínio (não reabrir sem motivo)

- **Não inventar intervalos de manutenção.** Recomendações do fabricante só entram com fonte validada (manual/versão).
- **Desconhecido não é zero.** Quilometragem, data, custo e aquisição ausentes ficam `NULL` e aparecem como "não informado"/"data desconhecida".
- Gravidade de problema é **percebida pelo usuário**, não diagnóstico. Alertas não devem afirmar defeito.
- Nenhuma exclusão de veículo pela interface (evita perda de histórico). Serviços e problemas podem ser excluídos com confirmação.

## Quilometragem

- A quilometragem atual é derivada da última leitura por data, sem campo duplicado no veículo.
- Uma leitura por veículo por dia (restrição no banco).
- `garage.models.odometer_conflict` compara apenas leituras de datas **estritamente anteriores e posteriores**; leituras do mesmo dia não são comparadas.
- Serviço com data e km cria/atualiza uma leitura com origem `service` (`maintenance.services.save_service`). Se já existir leitura manual no mesmo dia, ela é preservada e o serviço não cria outra. Excluir o serviço remove a leitura gerada por ele.
- A origem `service` não aparece no formulário manual de leituras.

## Plano e alertas

- **Sugestões não têm intervalos.** Um teste impede números de km/meses/anos nos motivos do catálogo (`planning/catalog.py`). Itens do fabricante ficam "a validar" até fonte informada e confirmada.
- A situação do item é derivada: próxima referência = último serviço ligado + intervalo (km ou meses, o que vier primeiro). Metas manuais (`next_km`/`next_date`) substituem o cálculo e são limpas quando um novo serviço é ligado a item recorrente.
- Ao criar serviço a partir do plano, `form.initial["plan"]` já vem preenchido. Só trate como "plano anterior" na edição (`form.instance.pk`), senão o plano nunca é atualizado.
- Item único realizado volta a pendente se o serviço for excluído ou desvinculado (`refresh_after_unlink`).
- Alertas não são gravados: `planning_overview(request)` calcula uma vez por requisição e é compartilhado pelo painel, página de alertas e contador do sino (`SimpleLazyObject`, só calcula se o template usar).
- Itens sem referência viram **um** alerta agrupado de prioridade baixa, para não poluir a lista após adicionar sugestões.
- Mensagens de alerta explicam o motivo e evitam "defeito"; há teste para isso.

## Histórico, finanças e backup

- A linha do tempo é montada em Python a partir das tabelas (sem tabela própria). Leituras criadas por serviços (origem `service`) ficam de fora para não duplicar o serviço.
- Totais usam apenas serviços com valor; os sem valor são contados à parte. Serviços sem data só entram em "Todo o período".
- A previsão por km usa a média de km/dia das leituras (mínimo de 30 dias entre a primeira e a última); sem isso, só itens com data entram.
- CSV: separador `;`, vírgula decimal e BOM UTF-8 (Excel pt-BR). Células que começam com `= + - @` recebem `'` (injeção de fórmulas).
- Backup: somente dados do dono, com campos listados explicitamente em `reports/backup.py` (`SECTIONS`). Ao criar campo novo em modelo exportado, **adicione-o em `SECTIONS`** e no teste de ida e volta; se o formato mudar de forma incompatível, suba `VERSION`.
- Restauração trata o zip como não confiável: lista fechada de nomes, limites de tamanho lidos de verdade (não só do cabeçalho), hash e tipo real dos anexos, `full_clean` em cada registro, transação única e remoção dos arquivos gravados se algo falhar. Nunca extrair pelo nome que vem no zip.
- A restauração só é permitida em conta sem veículos; mesclar backups exigiria resolver conflitos e não vale a complexidade.

## Assistente

- Regras em `assistant/knowledge.py` são dados: termos **normalizados** (minúsculas, sem acento), causas com tipo (inspeção ou diagnóstico) e `normal=True` quando pode ser comportamento normal. Testes impedem números de km/meses/anos e afirmações definitivas.
- Regras específicas são casadas por termos no texto; se nenhuma casar, usa a lista genérica do sintoma. Ordem das regras importa (a primeira causa aparece primeiro).
- Histórico evita investigações repetidas: causa com `ruled_out_terms` presentes em "causas descartadas" de um relato parecido vai para "Já descartado". Relato parecido = mesmo sintoma e mesmo local, ou 2+ palavras relevantes em comum.
- Urgência só sobe (`raise_to`) e sempre acumula justificativas: sinais de risco ou gravidade alta = alta; itens de segurança, relato parecido em aberto ou gravidade média = média.
- Perguntas acumulam em `analysis.questions` e são mescladas no fim; não sobrescreva a lista (a pergunta de garantia já se perdeu assim).
- O perfil de uso entra no backup (`SECTIONS`); o teste de ida e volta falha se um modelo novo com dados do dono ficar de fora, o que é o comportamento desejado.
- Menu superior com 7 itens: barra inferior até 1200 px. Teste 1180, 1220, 1300, 1440 e 1500 px.

## Interface

- Menu superior com 6 itens: ícones ocultos até 1440 px, espaçamento compacto até 1300 px e barra inferior até 1100 px (com 7 itens, até 1200 px).
- Links repetidos na página (ex.: "Serviços" na barra inferior e na lista de CSV) quebram seletores como `.last`; restrinja pelo contêiner (`.csv-links`).
- Gráficos com rolagem horizontal começam no fim (`scrollLeft = scrollWidth`) para mostrar os meses recentes no celular.
- O cabeçalho já transbordou duas vezes ao ganhar itens (700–1000 px com 5 itens; 1100–1440 px com 6). Sempre rode a jornada de navegador com as larguras acima.
- Regra base declarada **depois** de um media query com a mesma especificidade anula o media query (aconteceu com `.mobile-only`). Aumente a especificidade ou declare a base antes.
- Garagem, Seus dados e Alterar senha ficam no menu "Mais opções" (ícone no cabeçalho). O link "Garagem" também existe como link de voltar em páginas de veículo; nos testes, restrinja o seletor.

## Django

- **`TestCase` não executa `transaction.on_commit`.** Use `self.captureOnCommitCallbacks(execute=True)` para testar exclusão de arquivos.
- **Feche `FileResponse` nos testes** (`response.close()`) antes de excluir o arquivo; senão o Windows bloqueia.
- A remoção de arquivos após commit tolera `OSError` e registra aviso; nunca deixe essa falha derrubar a requisição, porque o banco já foi alterado.
- `RadioSelect.id_for_label` devolve vazio. Para ids de ajuda/erro use `field.auto_id` (em templates e no `StyledFormMixin`), o que também funciona com prefixos de formset.
- `DecimalField` com `pt-br` não aceita `1.234,56` sem `USE_THOUSAND_SEPARATOR`. Use `MoneyField`/`normalize_money` em `maintenance/forms.py`.
- Datas desconhecidas: ordenação com `F("date").desc(nulls_last=True)` em `Meta.ordering`.
- Campo removido condicionalmente do formulário (ex.: `resolves` sem problemas em aberto) faz o Django **ignorar** valores injetados. Para testar a validação, crie o cenário em que o campo existe.
- Alterar rótulos de `choices` gera migração `AlterField`; é esperado e não altera dados.
- Respostas HTMX parciais: use `vary_on_headers("HX-Request")` e `historyCacheSize: 0` para o botão Voltar não exibir só o fragmento.
- Rode sempre `manage.py makemigrations --check --dry-run` antes de commitar.

## Testes

- Unitários/HTTP: `manage.py test garage maintenance planning reports assistant`. Anexos usam `MEDIA_ROOT` temporário (`MediaTestCase`).
- Em helpers de teste, não use nomes de parâmetro que colidam com campos enviados via `**fields` (ex.: `plan`), senão dá `TypeError: got multiple values`.
- Navegador: `RUN_BROWSER_TESTS=1` + `manage.py test garage.test_browser`; usa banco temporário, nunca o `db.sqlite3` pessoal.
- **Playwright síncrono roda dentro de um loop asyncio**: consultar o ORM dentro de `with sync_playwright()` gera `SynchronousOnlyOperation`. Crie dados antes do bloco e obtenha ids pela interface (`page.url`, links).
- Capturas com `animations="disabled"`; sem isso a animação de entrada aparece esmaecida.
- Em captura `full_page`, a barra inferior fixa do celular aparece no meio da imagem. É artefato da captura, não bug.
- No celular a navegação superior fica oculta; clique pela `.bottom-nav`.
- `assertNotContains` com um rótulo que também existe nas opções de um `<select>` falha falsamente. Verifique textos exclusivos dos resultados.
- Os testes cobrem, em larguras de 360, 390 e 1280/1440 px, rolagem horizontal, erros de JavaScript e respostas HTTP >= 400.

## Segurança

- Toda consulta de veículo, serviço, problema e anexo filtra pelo proprietário (`vehicle__owner=request.user`); outro dono recebe 404.
- Anexos: tipo detectado pelo conteúdo (não pela extensão), nome aleatório, servidos apenas pela view autenticada com `Content-Security-Policy: sandbox`; PDF e HEIC são baixados, não exibidos.
- `next` na troca de veículo passa por `url_has_allowed_host_and_scheme`.
- A primeira conta só pode ser criada via localhost. Não há credenciais padrão; não crie usuários ou dados fictícios no banco pessoal.
- Metadados de fotos (ex.: localização) ainda não são removidos.

## Edição de código

- Ao substituir um bloco que termina antes da próxima declaração (`class ...`), inclua a declaração inteira no trecho; uma troca já apagou a linha `class ReadingFilterForm` em `garage/forms.py`. Releia o arquivo após edições grandes.
- Trechos de busca repetidos (ex.: comando `manage.py test garage`, que é prefixo de outro) fazem a substituição falhar; inclua contexto único.
