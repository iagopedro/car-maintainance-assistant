# Rodagem

Garagem pessoal para acompanhamento automotivo, em portugues do Brasil.

Antes de alterar regras, testes ou anexos, leia [docs/licoes-aprendidas.md](docs/licoes-aprendidas.md).

## Incremento 1

- Conta local inicial, login, logout por POST, troca de senha e bloqueio temporario apos cinco falhas de login.
- Cadastro e edicao de varios veiculos, separados por proprietario, e selecao de veiculo ativo.
- Dashboard com dados reais: ultima leitura, quantidade de registros e diferenca entre primeira e ultima leitura.
- Leituras de quilometragem com data, origem, observacao, filtros e paginacao.
- Validacao cronologica: leituras retroativas coerentes sao aceitas; retrocesso, data futura e duplicidade no mesmo dia sao rejeitados.
- Formularios responsivos, CSRF, escape de conteudo e recursos visuais servidos localmente.

## Incremento 2

- Botao **Registrar** (barra inferior no celular) com tres opcoes: servico, problema ou quilometragem.
- Servicos: so a categoria e obrigatoria. Titulo, data, km, valor e fotos ficam no primeiro bloco; tipo, oficina, pecas, custos detalhados, garantia e observacoes ficam em "Mais detalhes". Data em branco significa data desconhecida.
- Valores aceitam formatos como `89,90`, `1.234,56` e `R$ 150`. Com pecas e mao de obra, o total e calculado.
- Servico com data e km cria ou atualiza a leitura do odometro (origem "Registro de servico"); editar ou excluir o servico ajusta essa leitura. Se ja existir leitura no mesmo dia, ela e mantida.
- Problemas: sintoma em botoes, descricao, data, km, local e gravidade percebida. Diagnostico, causas descartadas, solucao e servico relacionado ficam em uma secao opcional. Acompanhamento cronologico ate a resolucao.
- Um servico pode resolver um problema em aberto; o problema e marcado como resolvido e ligado ao servico.
- Atalho para registrar o caso da agua na porta traseira como problema resolvido, com causas descartadas (combustivel, bomba, injecao) e data desconhecida. Aparece para um Compacto sem problemas registrados.
- Anexos privados (JPG, PNG, WEBP, HEIC, PDF, ate 10 MB, 10 por envio): tipo verificado pelo conteudo, nome aleatorio em `media/`, acesso somente pelo dono.
- Listas com busca, filtro por categoria/periodo, total registrado e abas de situacao para problemas. Exclusao com confirmacao.

Nao implementados ainda: linha do tempo unificada, relatorios financeiros, exportacao, backup automatizado, notificacoes fora do aplicativo e assistente de sintomas. As pendencias do painel sao cadastrais, nao diagnosticos mecanicos. Leituras manuais sao somente adicionadas e consultadas; edicao auditada e troca de odometro exigem uma evolucao especifica. Fotos nao tem metadados (como localizacao) removidos.

## Incremento 3

- **Plano de manutencao** (`/plano/`): itens com tipo (recomendacao do fabricante, preventiva pelo uso, inspecao sugerida, diagnostico profissional), prioridade, motivo, custo estimado e fonte.
- Repeticao por km e/ou meses (vale o que ocorrer primeiro) ou apenas proxima data/km. A proxima referencia e calculada a partir do ultimo servico ligado ao item.
- Situacoes: passou da referencia, chegando, atualize o km, sem referencia, programado, em dia, realizado e descartado. Acoes: registrar realizacao (abre o formulario de servico ja preenchido), programar data, vincular servico ja registrado, descartar com motivo e reativar.
- **Sugestoes** (`/plano/sugestoes/`): 16 itens comuns **sem intervalos**. Recomendacoes do fabricante ficam marcadas "a validar no manual" ate voce informar a fonte e confirmar.
- **Alertas** (`/alertas/`, sino no cabecalho e painel): itens atrasados ou chegando, itens sem referencia (agrupados), itens de diagnostico, programacao vencida, quilometragem desatualizada, problemas de gravidade alta ou sem acompanhamento, sintomas recorrentes e garantias terminando. Cada alerta explica o motivo, sem afirmar defeito.
- **Preferencias** (`/alertas/configurar/`): antecedencia em km e dias, lembrete de atualizar o km e prioridades exibidas. Os valores padrao (1.000 km, 30 dias) sao apenas antecedencia de aviso, nao intervalos de manutencao.
- No celular, a barra inferior passa a ter Inicio, Plano, Registrar, Servicos e Problemas; a Garagem fica no icone do cabecalho. A barra inferior e usada ate 1000 px de largura.

## Executar no Windows

Requer Python 3.13. Na pasta do projeto, usando PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Abra http://127.0.0.1:8000 e crie sua conta diretamente no navegador. Nao ha credenciais padrao. A criacao da primeira conta so aceita conexoes locais e fecha depois que existe um usuario. Nao publique essa etapa atras de um proxy: realize a configuracao local antes de qualquer exposicao externa.

O atalho do Compacto apenas preenche o formulario: Exemplo Compacto 2022 e motorizacao informada, nao validada. Nao cadastra o carro automaticamente, nao presume quilometragem, combustivel ou aquisicao e nao cria historico de manutencao. O caso da agua na porta tambem so preenche o formulario com o seu relato; nada e salvo sem confirmacao.

Textos pessoais do atalho (ex.: rotina de uso) ficam em `.local/presets.json`, fora do versionamento. Campos aceitos: `brand`, `model`, `version`, `model_year`, `manufacture_year`, `engine`, `fuel`, `plate`, `notes`. Exemplo:

```json
{"exemplo": {"notes": "Descreva aqui trajetos e condicoes de uso."}}
```

O servidor acima e de desenvolvimento, restrito ao computador. Para uso local prolongado, apos `collectstatic`, e possivel usar o servidor WSGI instalado:

```powershell
.\.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:8000 config.wsgi:application
```

Pare o servidor com Ctrl+C. Se a porta estiver ocupada, utilize outra, por exemplo 8001. Nao use `0.0.0.0` nem publique o servidor de desenvolvimento na internet. O acesso por celular requer configuracao posterior de rede/HTTPS; layout responsivo nao significa que o telefone ja consegue acessar o localhost do computador.

## Testar

```powershell
.\.venv\Scripts\python.exe manage.py test garage maintenance planning
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

O teste de navegador e opcional e usa banco temporario, sem inserir dados no banco pessoal:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m playwright install chromium
$env:RUN_BROWSER_TESTS = '1'
.\.venv\Scripts\python.exe manage.py test garage.test_browser -v 2
Remove-Item Env:RUN_BROWSER_TESTS
```

Capturas de tela ficam em `artifacts/`, fora do versionamento. A primeira jornada cobre criacao da conta, Compacto, edicao, leitura retroativa, filtros HTMX, rejeicao de inconsistencia, segundo veiculo, troca de veiculo ativo, troca de senha e login. A segunda, em celular, cobre registro de servico com pecas e anexos, caso da porta traseira, problema com acompanhamento ate a resolucao, filtro de servicos e exclusao. A terceira cobre sugestoes do plano, validacao da fonte, registro da ultima realizacao, alertas no painel, programacao e preferencias de alerta, com larguras de 360, 800, 1024 e 1280 pixels. As demais verificam 360, 390 e 1280/1440 pixels.

## Dados e recuperacao

O banco fica em `db.sqlite3`, os anexos em `media/` e a chave local gerada automaticamente em `.local/secret.key`. Os tres estao fora do versionamento; proteja-os pelas permissoes da sua conta do Windows e pelo backup do computador. SQLite nao fornece criptografia em repouso neste projeto.

Enquanto o backup automatizado nao existe, pare todos os processos do aplicativo antes de copiar o banco e as pastas `media` e `.local` para um local protegido. Restaure apenas com o aplicativo parado e usando uma versao compativel do projeto. A restauracao manual ainda nao integra a suite automatizada. CSV nao substituira backup.

Para recuperar acesso, execute localmente e digite a nova senha no terminal, nunca no chat:

```powershell
.\.venv\Scripts\python.exe manage.py changepassword SEU_USUARIO
```

O bloqueio por falhas expira apos 15 minutos. Placas, observacoes, servicos, problemas e anexos sao privados por proprietario. A interface nao permite exclusao de veiculos para evitar perda involuntaria de historico; servicos e problemas podem ser excluidos apos confirmacao.

## Arquitetura e evolucao

Monolito modular Django 5.2 LTS, SQLite, templates, Bootstrap e HTMX. `garage` cuida de veiculos e odometro; `maintenance` cuida de servicos, pecas, problemas, acompanhamento e anexos; `planning` cuida do plano, sugestoes e alertas. As regras de vencimento ficam em `planning/rules.py` (funcoes puras) e os alertas em `planning/alerts.py`, calculados a cada requisicao a partir dos dados, sem tabela de alertas. Regras ficam nos modelos e em `services.py` (transacoes); as views sempre filtram pelo proprietario. A quilometragem atual e derivada da ultima leitura cronologica, sem coluna duplicada que possa divergir. Uma leitura por veiculo por dia e uma restricao deliberada.

Fontes tecnicas e regras preventivas terao modelos proprios nos incrementos seguintes. A classificacao preventiva/corretiva dos servicos sera a base da comparacao financeira. Nao ha intervalos de manutencao presumidos. A validacao de motor, versao e manual sera obrigatoria antes de aplicar recomendacoes de fabricante.

Para nuvem: PostgreSQL com migracao de dados testada, armazenamento privado de anexos, HTTPS e rotina de backup/restauracao. A configuracao atual ainda e local. Em producao, definir `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY` e `DJANGO_ALLOWED_HOSTS`; cookies seguros e redirecionamento HTTPS sao ativados. Validar `manage.py check --deploy` e proxy confiavel antes da publicacao. Nao confiar automaticamente em cabecalhos de proxy.

As dependencias de execucao estao fixadas nas versoes instaladas e testadas; revisar atualizacoes de seguranca periodicamente. Recursos de terceiros e licencas estao em `static/vendor`. A ilustracao PNG e original e pode ser regenerada com `scripts/generate-artwork.ps1` no Windows. Nao representa uma fotografia do veiculo.